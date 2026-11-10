//! What the player is there to do: a mission as a run of stages, each with an objective to show
//! and something that ends it, and the things that happen along the way: people arriving,
//! words over the radio, charges going off.
//!
//! A mission never touches the game itself. Each frame it is told what is so (where the player
//! is, who is left alive, what has been used) and answers with what it wants done.

use crate::level::Level;
use glam::Vec3;
use std::collections::{HashMap, HashSet, VecDeque};

/// What ends a stage.
#[derive(Clone, Debug)]
pub enum Until {
    /// The player comes within this many metres of a `goal` marker.
    Reach(&'static str, f32),
    /// Everyone of these spawn groups is dead.
    Dead(&'static [&'static str]),
    /// The player has used this `use` marker.
    Used(&'static str),
    /// This many seconds have passed in the stage.
    Seconds(f32),
    /// Everyone of these groups is dead, or this long has passed.
    DeadOrSeconds(&'static [&'static str], f32),
}

/// Something a mission asks the game to do.
#[derive(Clone, Debug, PartialEq)]
pub enum Do {
    /// Bring the people of a spawn group into play.
    Spawn(&'static str),
    /// Words on the radio, with who says them.
    Say(&'static str, &'static str),
    /// Tell a group where the player is: they come looking.
    Alert(&'static str),
    Sound(&'static str),
    /// Set off an explosion at a `goal` marker.
    Explode(&'static str),
    /// Start something burning at a `goal` marker.
    Burn(&'static str),
    /// Remember this point: dying brings the player back here.
    Checkpoint,
    /// Change the weather over this many seconds.
    Weather(&'static str, f32),
    Complete,
}

/// One stage: what the player is told, where the marker on their view points, what happens as
/// it begins (each after a delay in seconds), and what ends it.
#[derive(Clone, Debug)]
pub struct Stage {
    pub objective: &'static str,
    pub goal: Option<&'static str>,
    pub begin: Vec<(f32, Do)>,
    pub until: Until,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Playing,
    Dead,
    Complete,
}

#[derive(Clone, Debug)]
pub struct Line {
    pub speaker: &'static str,
    pub text: &'static str,
    pub left: f32,
}

/// What a mission is told each frame.
pub struct Facts<'a> {
    pub player: Vec3,
    pub player_alive: bool,
    /// How many of each spawn group are alive.
    pub alive: &'a HashMap<String, u32>,
    pub used: &'a HashSet<String>,
}

pub struct Mission {
    pub title: &'static str,
    stages: Vec<Stage>,
    pub stage: usize,
    stage_time: f32,
    waiting: Vec<(f32, Do)>,
    pub state: State,
    pub lines: VecDeque<Line>,
    goals: HashMap<String, Vec3>,
    /// The stage a death returns the player to.
    pub checkpoint: usize,
    /// Seconds since the mission ended or the player died, for the screens that follow.
    pub ended_for: f32,
    /// Groups already brought into play, so that returning to a checkpoint doesn't double them.
    pub spawned: HashSet<&'static str>,
}

impl Mission {
    pub fn new(title: &'static str, stages: Vec<Stage>, level: &Level) -> Self {
        let goals = level
            .markers_of("goal")
            .map(|marker| (marker.name.clone(), marker.position))
            .collect();
        let mut mission = Self {
            title,
            stages,
            stage: 0,
            stage_time: 0.0,
            waiting: Vec::new(),
            state: State::Playing,
            lines: VecDeque::new(),
            goals,
            checkpoint: 0,
            ended_for: 0.0,
            spawned: HashSet::new(),
        };
        mission.enter(0);
        mission
    }

    fn enter(&mut self, stage: usize) {
        self.stage = stage;
        self.stage_time = 0.0;
        if let Some(entered) = self.stages.get(stage) {
            log::info!("mission: stage {stage}: {}", entered.objective);
            self.waiting.extend(entered.begin.iter().cloned());
        }
    }

    /// Which stage the mission is at, counting from nought.
    pub fn stage(&self) -> usize {
        self.stage
    }

    pub fn objective(&self) -> &'static str {
        match self.state {
            State::Complete => "",
            _ => self.stages.get(self.stage).map_or("", |stage| stage.objective),
        }
    }

    /// Where the marker on the player's view points.
    pub fn goal(&self) -> Option<Vec3> {
        let name = self.stages.get(self.stage)?.goal?;
        self.goals.get(name).copied()
    }

    pub fn goal_named(&self, name: &str) -> Option<Vec3> {
        self.goals.get(name).copied()
    }

    /// Goes back to the last checkpoint, as after a death.
    pub fn retry(&mut self) {
        self.state = State::Playing;
        self.ended_for = 0.0;
        self.waiting.clear();
        self.lines.clear();
        let stage = self.checkpoint;
        // What that stage began with happens again, but nobody is brought in twice.
        self.enter(stage);
        let spawned = &self.spawned;
        self.waiting
            .retain(|(_, action)| !matches!(action, Do::Spawn(group) if spawned.contains(group)));
    }

    /// Moves the mission on, and returns what it wants done now.
    pub fn update(&mut self, facts: &Facts<'_>, dt: f32) -> Vec<Do> {
        for line in &mut self.lines {
            line.left -= dt;
        }
        // One line at a time is on the radio; the rest wait their turn.
        while self.lines.front().is_some_and(|line| line.left <= 0.0) {
            self.lines.pop_front();
        }
        if self.state != State::Playing {
            self.ended_for += dt;
            return Vec::new();
        }
        if !facts.player_alive {
            self.state = State::Dead;
            self.ended_for = 0.0;
            return Vec::new();
        }
        self.stage_time += dt;
        let mut out = Vec::new();
        let mut index = 0;
        while index < self.waiting.len() {
            self.waiting[index].0 -= dt;
            if self.waiting[index].0 <= 0.0 {
                let (_, action) = self.waiting.remove(index);
                match action {
                    Do::Say(speaker, text) => {
                        // Long enough to read: a little for each word.
                        let words = text.split_whitespace().count() as f32;
                        let queued: f32 = self.lines.iter().map(|line| line.left.max(0.0)).sum();
                        let _ = queued;
                        self.lines.push_back(Line {
                            speaker,
                            text,
                            left: 1.6 + words * 0.36,
                        });
                        out.push(Do::Sound("radio"));
                    }
                    Do::Checkpoint => self.checkpoint = self.stage,
                    Do::Complete => {
                        self.state = State::Complete;
                        self.ended_for = 0.0;
                    }
                    Do::Spawn(group) => {
                        self.spawned.insert(group);
                        out.push(Do::Spawn(group));
                    }
                    other => out.push(other),
                }
            } else {
                index += 1;
            }
        }
        let Some(stage) = self.stages.get(self.stage) else {
            return out;
        };
        let dead = |groups: &[&str]| {
            // Only once they have had the time to arrive.
            self.stage_time > 1.0
                && groups
                    .iter()
                    .all(|group| facts.alive.get(*group).copied().unwrap_or(0) == 0)
        };
        let done = match &stage.until {
            Until::Reach(name, radius) => self
                .goals
                .get(*name)
                .is_some_and(|goal| goal.distance(facts.player) < *radius),
            Until::Dead(groups) => dead(groups),
            Until::Used(name) => facts.used.contains(*name),
            Until::Seconds(seconds) => self.stage_time >= *seconds,
            Until::DeadOrSeconds(groups, seconds) => dead(groups) || self.stage_time >= *seconds,
        };
        if done && self.stage + 1 < self.stages.len() {
            self.enter(self.stage + 1);
        }
        out
    }
}

/// A free roam with nothing to do: for levels that are only for looking round.
pub fn none(level: &Level) -> Mission {
    Mission::new(
        "",
        vec![Stage {
            objective: "",
            goal: None,
            begin: Vec::new(),
            until: Until::Seconds(f32::MAX),
        }],
        level,
    )
}

/// The mission a level asks for by name, in its `mission` setting.
pub fn by_name(name: &str, level: &Level) -> Mission {
    match name {
        "dead_air" => dead_air(level),
        _ => none(level),
    }
}

/// DEAD AIR. Alder Ridge has been under the Directorate for two years. Tonight the resistance
/// cell on Juniper Court means to blow the jammer that keeps the valley off the air.
pub fn dead_air(level: &Level) -> Mission {
    use Do::{Alert, Burn, Checkpoint, Complete, Explode, Say, Sound, Spawn, Weather};
    let stages = vec![
        Stage {
            objective: "Take the carbine and meet Mara at the garage door",
            goal: Some("garage_door"),
            begin: vec![
                (0.0, Spawn("cell")),
                (1.5, Say("MARA", "That's the last of the curfew patrols past the window. If we're going, it's now.")),
                (7.5, Say("MARA", "Jammer's at the filling station on Alder. Dunn and I will be right behind you.")),
            ],
            until: Until::Reach("garage_door", 2.5),
        },
        Stage {
            objective: "Cut through the back yards to Alder Street",
            goal: Some("yards"),
            begin: vec![
                (0.0, Checkpoint),
                (0.0, Spawn("patrol")),
                (0.5, Say("DUNN", "Keep it quiet through the yards. Two of them walk the alley every few minutes.")),
            ],
            until: Until::Reach("yards", 6.0),
        },
        Stage {
            objective: "Clear the patrol",
            goal: None,
            begin: vec![
                (0.0, Alert("patrol")),
                (0.4, Say("MARA", "They've seen us. Put them down before they call it in.")),
            ],
            until: Until::Dead(&["patrol"]),
        },
        Stage {
            objective: "Reach the checkpoint on Alder Street",
            goal: Some("checkpoint"),
            begin: vec![
                (0.0, Checkpoint),
                (0.0, Spawn("checkpoint")),
                (1.0, Say("DUNN", "That'll have woken the checkpoint. Use the cars. Don't stand in the road.")),
            ],
            until: Until::Reach("checkpoint", 22.0),
        },
        Stage {
            objective: "Clear the checkpoint",
            goal: Some("checkpoint"),
            begin: vec![
                (0.0, Alert("checkpoint")),
                (0.5, Say("MARA", "Sandbags on the left, gun truck behind the barrier. Work round them.")),
            ],
            until: Until::Dead(&["checkpoint"]),
        },
        Stage {
            objective: "Plant the charge on the jammer truck",
            goal: Some("jammer"),
            begin: vec![
                (0.0, Checkpoint),
                (0.0, Spawn("station")),
                (1.0, Say("MARA", "Checkpoint's ours. The jammer's the truck with the mast, on the forecourt.")),
            ],
            until: Until::Used("jammer"),
        },
        Stage {
            objective: "Get clear of the blast",
            goal: Some("rally"),
            begin: vec![
                (0.0, Say("DUNN", "Charge is set. Thirty seconds. Move!")),
                (0.0, Sound("charge_armed")),
                (2.0, Spawn("reinforcements")),
                (3.0, Alert("reinforcements")),
            ],
            until: Until::Seconds(14.0),
        },
        Stage {
            objective: "Hold until the jammer blows",
            goal: Some("rally"),
            begin: vec![(8.0, Say("MARA", "Truck coming up Alder. Hold them off the forecourt!"))],
            until: Until::Seconds(16.0),
        },
        Stage {
            objective: "Finish them",
            goal: None,
            begin: vec![
                (0.0, Explode("jammer")),
                (0.1, Burn("jammer")),
                (0.3, Explode("jammer_b")),
                (1.2, Say("MARA", "That's it. That's the jammer. Listen... the radio's back.")),
                (2.0, Weather("fair", 60.0)),
            ],
            until: Until::DeadOrSeconds(&["reinforcements", "station"], 75.0),
        },
        Stage {
            objective: "",
            goal: None,
            begin: vec![
                (1.0, Say("RADIO", "...this is Free Cascadia on the open band. If you can hear this, you are not alone.")),
                (9.0, Complete),
            ],
            until: Until::Seconds(f32::MAX),
        },
    ];
    Mission::new("DEAD AIR", stages, level)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn level() -> Level {
        Level::parse("marker goal door 10 0 0 0\nmarker goal far 50 0 0 0\n").unwrap()
    }

    fn stages() -> Vec<Stage> {
        vec![
            Stage {
                objective: "Go to the door",
                goal: Some("door"),
                begin: vec![(0.0, Do::Spawn("guards")), (1.0, Do::Say("A", "one two three"))],
                until: Until::Reach("door", 2.0),
            },
            Stage {
                objective: "Clear them",
                goal: None,
                begin: vec![(0.0, Do::Checkpoint)],
                until: Until::Dead(&["guards"]),
            },
            Stage {
                objective: "",
                goal: None,
                begin: vec![(0.5, Do::Complete)],
                until: Until::Seconds(f32::MAX),
            },
        ]
    }

    #[test]
    fn a_mission_runs_through_its_stages() {
        let mut mission = Mission::new("T", stages(), &level());
        let mut alive = HashMap::new();
        let used = HashSet::new();
        fn facts<'a>(player: Vec3, alive: &'a HashMap<String, u32>, used: &'a HashSet<String>) -> Facts<'a> {
            Facts {
                player,
                player_alive: true,
                alive,
                used,
            }
        }
        let did = mission.update(&facts(Vec3::ZERO, &alive, &used), 0.1);
        assert_eq!(did, vec![Do::Spawn("guards")]);
        alive.insert("guards".to_owned(), 2);
        assert_eq!(mission.objective(), "Go to the door");
        assert_eq!(mission.goal(), Some(Vec3::new(10.0, 0.0, 0.0)));
        // The line comes after its delay, with the radio's click.
        let did = mission.update(&facts(Vec3::ZERO, &alive, &used), 1.0);
        assert_eq!(did, vec![Do::Sound("radio")]);
        assert_eq!(mission.lines.len(), 1);
        mission.update(&facts(Vec3::new(9.0, 0.0, 0.0), &alive, &used), 0.1);
        assert_eq!(mission.stage, 1);
        for _ in 0..20 {
            mission.update(&facts(Vec3::new(9.0, 0.0, 0.0), &alive, &used), 0.1);
        }
        assert_eq!(mission.stage, 1, "the guards still live");
        assert_eq!(mission.checkpoint, 1);
        alive.insert("guards".to_owned(), 0);
        mission.update(&facts(Vec3::new(9.0, 0.0, 0.0), &alive, &used), 0.1);
        assert_eq!(mission.stage, 2);
        mission.update(&facts(Vec3::new(9.0, 0.0, 0.0), &alive, &used), 1.0);
        assert_eq!(mission.state, State::Complete);
    }

    #[test]
    fn dying_stops_it_and_a_retry_goes_back_to_the_checkpoint() {
        let mut mission = Mission::new("T", stages(), &level());
        let alive: HashMap<String, u32> = [("guards".to_owned(), 2)].into();
        let used = HashSet::new();
        let facts = |player_alive: bool| Facts {
            player: Vec3::new(10.0, 0.0, 0.0),
            player_alive,
            alive: &alive,
            used: &used,
        };
        mission.update(&facts(true), 0.1);
        mission.update(&facts(true), 0.1);
        assert_eq!(mission.stage, 1);
        mission.update(&facts(false), 0.1);
        assert_eq!(mission.state, State::Dead);
        mission.retry();
        assert_eq!((mission.state, mission.stage), (State::Playing, 1));
        // The guards were brought in before the checkpoint: they are not brought in again.
        let did = mission.update(&facts(true), 0.1);
        assert!(!did.contains(&Do::Spawn("guards")), "{did:?}");
    }
}
