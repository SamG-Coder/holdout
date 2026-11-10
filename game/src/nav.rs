//! Where people can walk, and where they can hide. The level's collision is sounded with rays
//! on a grid: wherever there is floor with headroom is somewhere to stand, neighbouring places
//! a step apart are joined, and places beside something solid are remembered as cover.
//!
//! A column of the grid can hold more than one floor, so an upstairs room and the room below
//! it are both walkable, and joined only by the stairs.

use crate::physics::{Physics, WORLD};
use glam::Vec3;
use std::cell::RefCell;
use std::cmp::Ordering;
use std::collections::BinaryHeap;

/// Metres between places.
pub const CELL: f32 = 0.5;
/// How much higher or lower a neighbour may be and still be a step away.
const MAX_STEP: f32 = 0.45;
/// Headroom a place needs.
const HEADROOM: f32 = 1.7;
/// How near a wall the middle of a body may come.
const CLEARANCE: f32 = 0.2;
const NONE: u32 = u32::MAX;
/// The eight ways to a neighbour: the four straight ones first.
const WAYS: [(i32, i32); 8] = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)];

#[derive(Clone, Copy, Debug)]
struct Place {
    position: Vec3,
    links: [u32; 8],
    /// Which connected part of the level it is in.
    region: u32,
}

/// Somewhere to shelter: beside something solid.
#[derive(Clone, Copy, Debug)]
pub struct Cover {
    pub position: Vec3,
    /// The way to what gives the shelter, flat on the ground.
    pub toward: Vec3,
    /// Low cover hides someone crouching, who can stand to shoot over it. High cover hides
    /// someone standing.
    pub low: bool,
    pub place: u32,
}

pub struct Nav {
    min_x: f32,
    min_z: f32,
    columns: usize,
    rows: usize,
    /// For each column of the grid, its places, lowest first: a run of `places`.
    column_first: Vec<u32>,
    column_count: Vec<u8>,
    places: Vec<Place>,
    pub covers: Vec<Cover>,
    /// What a search writes as it goes, kept from one search to the next.
    scratch: RefCell<Scratch>,
}

/// The working of a search for a way: what it costs to reach each place, and from where. A
/// place's entry counts only if it carries the number of the search in hand, so that nothing
/// need be wiped between searches.
#[derive(Default)]
struct Scratch {
    search: u32,
    stamp: Vec<u32>,
    cost: Vec<f32>,
    came: Vec<u32>,
}

#[derive(Clone, Copy, PartialEq)]
struct Open {
    cost: f32,
    place: u32,
}

impl Eq for Open {}

impl Ord for Open {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
    }
}

impl PartialOrd for Open {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Nav {
    /// Sounds the level between two corners (their Y is the range of heights to look in), and
    /// keeps what can be reached from `seeds`: the places people start.
    pub fn build(physics: &Physics, low: Vec3, high: Vec3, seeds: &[Vec3]) -> Self {
        let columns = (((high.x - low.x) / CELL).ceil() as usize).max(1);
        let rows = (((high.z - low.z) / CELL).ceil() as usize).max(1);
        let mut nav = Self {
            min_x: low.x,
            min_z: low.z,
            columns,
            rows,
            column_first: vec![0; columns * rows],
            column_count: vec![0; columns * rows],
            places: Vec::new(),
            covers: Vec::new(),
            scratch: RefCell::new(Scratch::default()),
        };
        // What stands close beside each place, by straight way: for cover.
        let mut walls: Vec<u8> = Vec::new();
        for row in 0..rows {
            for column in 0..columns {
                let x = low.x + (column as f32 + 0.5) * CELL;
                let z = low.z + (row as f32 + 0.5) * CELL;
                let index = row * columns + column;
                nav.column_first[index] = nav.places.len() as u32;
                let mut found: Vec<(Vec3, u8)> = Vec::new();
                let mut from = high.y;
                for _ in 0..4 {
                    if from <= low.y {
                        break;
                    }
                    let Some(hit) = physics.raycast(Vec3::new(x, from, z), Vec3::NEG_Y, from - low.y, WORLD) else {
                        break;
                    };
                    from = hit.point.y - 0.3;
                    if hit.normal.y < 0.72 {
                        continue;
                    }
                    let floor = hit.point;
                    if physics
                        .raycast(floor + Vec3::Y * 0.25, Vec3::Y, HEADROOM - 0.25, WORLD)
                        .is_some()
                    {
                        continue;
                    }
                    // Too near a wall, the middle of a body can't stand here; a little
                    // further off, the wall is cover.
                    let mut crowded = false;
                    let mut beside = 0u8;
                    for (way, &(dx, dz)) in WAYS[..4].iter().enumerate() {
                        let direction = Vec3::new(dx as f32, 0.0, dz as f32);
                        if let Some(wall) = physics.raycast(floor + Vec3::Y * 0.55, direction, 0.85, WORLD) {
                            if wall.distance < CLEARANCE {
                                crowded = true;
                                break;
                            }
                            beside |= 1 << way;
                        }
                    }
                    if !crowded {
                        found.push((floor, beside));
                    }
                }
                found.sort_by(|a, b| a.0.y.total_cmp(&b.0.y));
                nav.column_count[index] = found.len() as u8;
                for (position, beside) in found {
                    nav.places.push(Place {
                        position,
                        links: [NONE; 8],
                        region: NONE,
                    });
                    walls.push(beside);
                }
            }
        }

        // Join neighbours a step apart. A diagonal needs both of the straight ways round it.
        for row in 0..rows {
            for column in 0..columns {
                let index = row * columns + column;
                let first = nav.column_first[index];
                for offset in 0..u32::from(nav.column_count[index]) {
                    let place = first + offset;
                    let y = nav.places[place as usize].position.y;
                    for way in 0..4 {
                        let (dx, dz) = WAYS[way];
                        nav.places[place as usize].links[way] = nav
                            .place_in(column as i32 + dx, row as i32 + dz, y, MAX_STEP)
                            .unwrap_or(NONE);
                    }
                }
            }
        }
        for place in 0..nav.places.len() {
            for way in 4..8 {
                let (a, b) = match way {
                    4 => (0, 1),
                    5 => (2, 1),
                    6 => (2, 3),
                    _ => (0, 3),
                };
                let first = nav.places[place].links[a];
                let second = nav.places[place].links[b];
                if first == NONE || second == NONE {
                    continue;
                }
                // The corner is reached the same going either way round.
                let via_first = nav.places[first as usize].links[b];
                let via_second = nav.places[second as usize].links[a];
                if via_first != NONE && via_first == via_second {
                    nav.places[place].links[way] = via_first;
                }
            }
        }

        // Regions: everything that can be walked to from each seed.
        let mut region = 0;
        for seed in seeds {
            let Some(start) = nav.nearest_any(*seed, 3.0) else {
                continue;
            };
            if nav.places[start as usize].region != NONE {
                continue;
            }
            let mut stack = vec![start];
            nav.places[start as usize].region = region;
            while let Some(place) = stack.pop() {
                for way in 0..8 {
                    let next = nav.places[place as usize].links[way];
                    if next != NONE && nav.places[next as usize].region == NONE {
                        nav.places[next as usize].region = region;
                        stack.push(next);
                    }
                }
            }
            region += 1;
        }

        // Cover: places with something solid close beside them, thinned so that they stand
        // apart. Whether it is low or high is one more ray, at head height.
        let mut taken: Vec<Vec3> = Vec::new();
        for (index, place) in nav.places.iter().enumerate() {
            if place.region == NONE || walls[index] == 0 {
                continue;
            }
            for (way, &(dx, dz)) in WAYS[..4].iter().enumerate() {
                if walls[index] & (1 << way) == 0 {
                    continue;
                }
                let toward = Vec3::new(dx as f32, 0.0, dz as f32);
                if taken
                    .iter()
                    .any(|other| other.distance_squared(place.position) < 1.1 * 1.1)
                {
                    continue;
                }
                let low = physics
                    .raycast(place.position + Vec3::Y * 1.5, toward, 1.1, WORLD)
                    .is_none();
                taken.push(place.position);
                nav.covers.push(Cover {
                    position: place.position,
                    toward,
                    low,
                    place: index as u32,
                });
            }
        }
        nav
    }

    pub fn place_count(&self) -> usize {
        self.places.len()
    }

    fn column_of(&self, x: f32, z: f32) -> (i32, i32) {
        (
            ((x - self.min_x) / CELL).floor() as i32,
            ((z - self.min_z) / CELL).floor() as i32,
        )
    }

    /// The place in a column whose height is within `tolerance` of `y`, nearest it.
    fn place_in(&self, column: i32, row: i32, y: f32, tolerance: f32) -> Option<u32> {
        if column < 0 || row < 0 || column >= self.columns as i32 || row >= self.rows as i32 {
            return None;
        }
        let index = row as usize * self.columns + column as usize;
        let first = self.column_first[index];
        (first..first + u32::from(self.column_count[index]))
            .map(|place| (place, (self.places[place as usize].position.y - y).abs()))
            .filter(|(_, apart)| *apart <= tolerance)
            .min_by(|a, b| a.1.total_cmp(&b.1))
            .map(|(place, _)| place)
    }

    /// The place nearest a point, within `reach`, whether or not it can be reached from anywhere.
    fn nearest_any(&self, point: Vec3, reach: f32) -> Option<u32> {
        let (column, row) = self.column_of(point.x, point.z);
        let span = (reach / CELL).ceil() as i32;
        let mut best: Option<(u32, f32)> = None;
        for dz in -span..=span {
            for dx in -span..=span {
                let (c, r) = (column + dx, row + dz);
                if c < 0 || r < 0 || c >= self.columns as i32 || r >= self.rows as i32 {
                    continue;
                }
                let index = r as usize * self.columns + c as usize;
                let first = self.column_first[index];
                for place in first..first + u32::from(self.column_count[index]) {
                    let position = self.places[place as usize].position;
                    // Height counts for more: the floor above is not near.
                    let apart = (position - point) * Vec3::new(1.0, 2.5, 1.0);
                    let distance = apart.length_squared();
                    if distance <= reach * reach * 2.5 && best.is_none_or(|(_, d)| distance < d) {
                        best = Some((place, distance));
                    }
                }
            }
        }
        best.map(|(place, _)| place)
    }

    /// The reachable place nearest a point, within `reach`.
    pub fn nearest(&self, point: Vec3, reach: f32) -> Option<u32> {
        let (column, row) = self.column_of(point.x, point.z);
        let span = (reach / CELL).ceil() as i32;
        let mut best: Option<(u32, f32)> = None;
        for dz in -span..=span {
            for dx in -span..=span {
                let (c, r) = (column + dx, row + dz);
                if c < 0 || r < 0 || c >= self.columns as i32 || r >= self.rows as i32 {
                    continue;
                }
                let index = r as usize * self.columns + c as usize;
                let first = self.column_first[index];
                for place in first..first + u32::from(self.column_count[index]) {
                    if self.places[place as usize].region == NONE {
                        continue;
                    }
                    let position = self.places[place as usize].position;
                    let apart = (position - point) * Vec3::new(1.0, 2.5, 1.0);
                    let distance = apart.length_squared();
                    if best.is_none_or(|(_, d)| distance < d) {
                        best = Some((place, distance));
                    }
                }
            }
        }
        best.map(|(place, _)| place)
    }

    pub fn position(&self, place: u32) -> Vec3 {
        self.places[place as usize].position
    }

    /// Whether two points are in the same connected part of the level.
    pub fn connected(&self, a: Vec3, b: Vec3) -> bool {
        match (self.nearest(a, 2.0), self.nearest(b, 2.0)) {
            (Some(a), Some(b)) => self.places[a as usize].region == self.places[b as usize].region,
            _ => false,
        }
    }

    /// Whether someone can walk straight from one point to another.
    pub fn clear_walk(&self, from: Vec3, to: Vec3) -> bool {
        let Some(mut place) = self.nearest(from, 1.0) else {
            return false;
        };
        let span = to - from;
        let length = (span.x * span.x + span.z * span.z).sqrt();
        let steps = (length / (CELL * 0.5)).ceil().max(1.0) as u32;
        for step in 1..=steps {
            let point = from + span * (step as f32 / steps as f32);
            let (column, row) = self.column_of(point.x, point.z);
            let y = self.places[place as usize].position.y;
            let Some(next) = self.place_in(column, row, y, MAX_STEP) else {
                return false;
            };
            if next != place {
                // It must be a neighbour joined to the last: no stepping through a wall.
                if !self.places[place as usize].links.contains(&next) {
                    return false;
                }
                place = next;
            }
        }
        true
    }

    /// The way to walk from one point to another: the corners to turn at, ending at the place
    /// nearest `to`. `None` if there is no way, or it is too far to be worth finding.
    pub fn path(&self, from: Vec3, to: Vec3) -> Option<Vec<Vec3>> {
        // Enough to cross the largest level; a search that needs more has lost its way.
        const MOST_VISITS: usize = 160_000;
        let start = self.nearest(from, 2.5)?;
        let goal = self.nearest(to, 2.5)?;
        if self.places[start as usize].region != self.places[goal as usize].region {
            return None;
        }
        if start == goal {
            return Some(vec![self.position(goal)]);
        }
        let goal_position = self.position(goal);
        // Leaning on the estimate a little makes for a far narrower search, and a way a few
        // per cent longer than the best at worst.
        let estimate = |place: u32| {
            let apart = self.places[place as usize].position - goal_position;
            let (dx, dz) = (apart.x.abs(), apart.z.abs());
            // The length of the shortest way on a grid joined eight ways.
            (dx.max(dz) + (std::f32::consts::SQRT_2 - 1.0) * dx.min(dz) + apart.y.abs()) * 1.2
        };
        let mut scratch = self.scratch.borrow_mut();
        let scratch = &mut *scratch;
        if scratch.stamp.len() != self.places.len() {
            scratch.stamp = vec![0; self.places.len()];
            scratch.cost = vec![0.0; self.places.len()];
            scratch.came = vec![NONE; self.places.len()];
            scratch.search = 0;
        }
        scratch.search = scratch.search.wrapping_add(1);
        if scratch.search == 0 {
            scratch.stamp.fill(0);
            scratch.search = 1;
        }
        let search = scratch.search;
        let mut open = BinaryHeap::new();
        scratch.stamp[start as usize] = search;
        scratch.cost[start as usize] = 0.0;
        scratch.came[start as usize] = NONE;
        open.push(Open {
            cost: estimate(start),
            place: start,
        });
        let mut visits = 0;
        let mut found = false;
        while let Some(Open { place, cost: priority }) = open.pop() {
            if place == goal {
                found = true;
                break;
            }
            // Left over from before a better way to it was found.
            if priority > scratch.cost[place as usize] + estimate(place) + 1.0e-3 {
                continue;
            }
            visits += 1;
            if visits > MOST_VISITS {
                break;
            }
            let here = self.places[place as usize];
            for way in 0..8 {
                let next = here.links[way];
                if next == NONE {
                    continue;
                }
                let step = (self.places[next as usize].position - here.position).length();
                let through = scratch.cost[place as usize] + step;
                let known = scratch.stamp[next as usize] == search;
                if !known || through < scratch.cost[next as usize] {
                    scratch.stamp[next as usize] = search;
                    scratch.cost[next as usize] = through;
                    scratch.came[next as usize] = place;
                    open.push(Open {
                        cost: through + estimate(next),
                        place: next,
                    });
                }
            }
        }
        if !found {
            return None;
        }
        let came = &scratch.came;
        let mut cells = vec![goal];
        let mut at = goal;
        while came[at as usize] != NONE {
            at = came[at as usize];
            cells.push(at);
        }
        cells.reverse();
        // Pull the string tight: keep only the places where the way must turn.
        let points: Vec<Vec3> = cells.iter().map(|&c| self.position(c)).collect();
        let mut corners = Vec::new();
        let mut anchor = 0;
        while anchor < points.len() - 1 {
            let mut reach = anchor + 1;
            let mut probe = points.len() - 1;
            // The furthest place that can be walked to straight from the anchor.
            while probe > anchor + 1 {
                if self.clear_walk(points[anchor], points[probe]) {
                    reach = probe;
                    break;
                }
                probe = anchor + (probe - anchor) / 2;
            }
            // The halving may have stopped short: step on while the way stays clear.
            while reach + 1 < points.len() && self.clear_walk(points[anchor], points[reach + 1]) {
                reach += 1;
            }
            corners.push(points[reach]);
            anchor = reach;
        }
        Some(corners)
    }

    /// A reachable place about `distance` from `centre`, in a direction picked by `turn` (0..1).
    pub fn around(&self, centre: Vec3, distance: f32, turn: f32) -> Option<Vec3> {
        let angle = turn * std::f32::consts::TAU;
        let wanted = centre + Vec3::new(angle.cos(), 0.0, angle.sin()) * distance;
        let place = self.nearest(wanted, 2.5)?;
        let home = self.nearest(centre, 2.5)?;
        (self.places[place as usize].region == self.places[home as usize].region)
            .then(|| self.position(place))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A yard 20 m square, with a wall across the middle that has a gap at one end, and a
    /// low crate.
    fn yard() -> Physics {
        let mut physics = Physics::new();
        physics.add_blocker(Vec3::new(0.0, -0.5, 0.0), Vec3::new(20.0, 1.0, 20.0), 0.0);
        physics.add_blocker(Vec3::new(-2.0, 1.5, 0.0), Vec3::new(16.0, 3.0, 0.4), 0.0);
        physics.add_blocker(Vec3::new(4.0, 0.5, 5.0), Vec3::new(1.2, 1.0, 1.2), 0.0);
        physics.step(1.0 / 60.0);
        physics
    }

    fn nav() -> Nav {
        let physics = yard();
        Nav::build(
            &physics,
            Vec3::new(-10.0, -1.0, -10.0),
            Vec3::new(10.0, 4.0, 10.0),
            &[Vec3::new(0.0, 0.0, 5.0)],
        )
    }

    #[test]
    fn the_way_goes_round_the_wall_through_its_gap() {
        let nav = nav();
        let from = Vec3::new(-6.0, 0.0, 5.0);
        let to = Vec3::new(-6.0, 0.0, -5.0);
        assert!(!nav.clear_walk(from, to), "the wall is in the way");
        let path = nav.path(from, to).expect("there is a way round");
        let mut length = 0.0;
        let mut at = from;
        for corner in &path {
            length += corner.distance(at);
            at = *corner;
        }
        assert!(path.len() >= 2 && path.len() <= 6, "{} corners", path.len());
        assert!(path.iter().any(|p| p.x > 5.5), "it goes through the gap: {path:?}");
        assert!(length > 24.0 && length < 34.0, "{length} m");
        assert!(path.last().unwrap().distance(to) < 1.0);
    }

    #[test]
    fn open_ground_is_walked_straight() {
        let nav = nav();
        let from = Vec3::new(-6.0, 0.0, 8.0);
        let to = Vec3::new(8.0, 0.0, 7.0);
        assert!(nav.clear_walk(from, to));
        assert_eq!(nav.path(from, to).unwrap().len(), 1);
    }

    #[test]
    fn nobody_walks_on_top_of_the_wall_or_through_the_crate() {
        let nav = nav();
        assert!(!nav.clear_walk(Vec3::new(2.0, 0.0, 5.0), Vec3::new(6.0, 0.0, 5.0)));
        // The crate's top is a floor with headroom, but it can't be reached.
        let on_crate = nav.nearest(Vec3::new(4.0, 1.0, 5.0), 0.4);
        assert!(on_crate.is_none_or(|p| nav.position(p).y < 0.5));
    }

    #[test]
    fn cover_is_found_beside_the_crate_and_the_wall() {
        let nav = nav();
        let low: Vec<_> = nav.covers.iter().filter(|c| c.low).collect();
        let high: Vec<_> = nav.covers.iter().filter(|c| !c.low).collect();
        assert!(
            low.iter().any(|c| c.position.distance(Vec3::new(4.0, 0.0, 5.0)) < 1.6),
            "low cover by the crate"
        );
        assert!(
            high.iter().any(|c| c.position.z.abs() < 1.2 && c.position.x < 5.0),
            "high cover by the wall"
        );
        // Each points at what shelters it.
        for cover in &nav.covers {
            assert!((cover.toward.length() - 1.0).abs() < 1.0e-5);
        }
    }
}
