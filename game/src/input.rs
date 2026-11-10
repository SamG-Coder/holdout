//! What the player is asking for, whatever they ask with: the page and the desktop window both
//! report keys by their `KeyboardEvent.code` names, mouse buttons by name, and mouse motion in
//! pixels.

/// Something the player can do.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(usize)]
pub enum Action {
    Forward,
    Back,
    Left,
    Right,
    Jump,
    Crouch,
    Sprint,
    Fire,
    Aim,
    Reload,
    Use,
    Grenade,
    Melee,
    Primary,
    Secondary,
    SwapWeapon,
    Pause,
    /// Leaves the body and flies the camera: for looking at the level while making it.
    Fly,
    FlyUp,
    FlyDown,
    Count,
}

const ACTIONS: usize = Action::Count as usize;

/// The action a key does, by its `KeyboardEvent.code`.
pub fn action_of_key(code: &str) -> Option<Action> {
    Some(match code {
        "KeyW" | "ArrowUp" => Action::Forward,
        "KeyS" | "ArrowDown" => Action::Back,
        "KeyA" | "ArrowLeft" => Action::Left,
        "KeyD" | "ArrowRight" => Action::Right,
        "Space" => Action::Jump,
        "KeyC" | "ControlLeft" => Action::Crouch,
        "ShiftLeft" | "ShiftRight" => Action::Sprint,
        "KeyR" => Action::Reload,
        "KeyE" | "KeyF" => Action::Use,
        "KeyG" => Action::Grenade,
        "KeyV" => Action::Melee,
        "Digit1" => Action::Primary,
        "Digit2" => Action::Secondary,
        "KeyQ" => Action::SwapWeapon,
        "Escape" | "KeyP" => Action::Pause,
        "F2" => Action::Fly,
        "PageUp" => Action::FlyUp,
        "PageDown" => Action::FlyDown,
        _ => return None,
    })
}

/// The action a mouse button does: `left`, `right` or `middle`.
pub fn action_of_button(button: &str) -> Option<Action> {
    Some(match button {
        "left" => Action::Fire,
        "right" => Action::Aim,
        "middle" => Action::Melee,
        _ => return None,
    })
}

/// The state of every action, and the mouse's motion since the last frame.
#[derive(Clone, Debug)]
pub struct Input {
    held: [bool; ACTIONS],
    /// Went down since the last frame, even if it has come up again since.
    pressed: [bool; ACTIONS],
    released: [bool; ACTIONS],
    /// Pixels the mouse has moved, right and down, since the last frame.
    pub look: (f32, f32),
    /// Notches the wheel has turned since the last frame, away from the player being positive.
    pub wheel: f32,
    /// A stick's push, each axis from -1 to 1, right and forward: a gamepad or a touch stick.
    pub stick: (f32, f32),
    /// A second stick's turn, in the same units as `look` per second.
    pub stick_look: (f32, f32),
    /// Radians a pixel of mouse motion turns the view.
    pub sensitivity: f32,
    pub invert_y: bool,
}

impl Default for Input {
    fn default() -> Self {
        Self {
            held: [false; ACTIONS],
            pressed: [false; ACTIONS],
            released: [false; ACTIONS],
            look: (0.0, 0.0),
            wheel: 0.0,
            stick: (0.0, 0.0),
            stick_look: (0.0, 0.0),
            sensitivity: 0.0022,
            invert_y: false,
        }
    }
}

impl Input {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set(&mut self, action: Action, down: bool) {
        let index = action as usize;
        if down && !self.held[index] {
            self.pressed[index] = true;
        }
        if !down && self.held[index] {
            self.released[index] = true;
        }
        self.held[index] = down;
    }

    /// A key going down or up, by its `KeyboardEvent.code`.
    pub fn key(&mut self, code: &str, down: bool) {
        if let Some(action) = action_of_key(code) {
            self.set(action, down);
        }
    }

    /// A mouse button going down or up.
    pub fn button(&mut self, button: &str, down: bool) {
        if let Some(action) = action_of_button(button) {
            self.set(action, down);
        }
    }

    pub fn mouse_motion(&mut self, x: f32, y: f32) {
        self.look.0 += x;
        self.look.1 += y;
    }

    pub fn held(&self, action: Action) -> bool {
        self.held[action as usize]
    }

    pub fn pressed(&self, action: Action) -> bool {
        self.pressed[action as usize]
    }

    pub fn released(&self, action: Action) -> bool {
        self.released[action as usize]
    }

    /// Takes a press, so that nothing else acts on it this frame.
    pub fn take(&mut self, action: Action) -> bool {
        std::mem::take(&mut self.pressed[action as usize])
    }

    /// How hard the player pushes right and forward, each from -1 to 1.
    pub fn movement(&self) -> (f32, f32) {
        let axis = |positive: Action, negative: Action| {
            f32::from(u8::from(self.held(positive))) - f32::from(u8::from(self.held(negative)))
        };
        let right = (axis(Action::Right, Action::Left) + self.stick.0).clamp(-1.0, 1.0);
        let forward = (axis(Action::Forward, Action::Back) + self.stick.1).clamp(-1.0, 1.0);
        (right, forward)
    }

    /// How far to turn the view this frame, in radians: to the left, and up.
    pub fn turn(&self, seconds: f32) -> (f32, f32) {
        let x = self.look.0 + self.stick_look.0 * seconds;
        let y = self.look.1 + self.stick_look.1 * seconds;
        let up = if self.invert_y { y } else { -y };
        (-x * self.sensitivity, up * self.sensitivity)
    }

    /// Lets every key and button go, for when the window loses focus.
    pub fn release_all(&mut self) {
        for index in 0..ACTIONS {
            if self.held[index] {
                self.released[index] = true;
            }
            self.held[index] = false;
        }
        self.stick = (0.0, 0.0);
        self.stick_look = (0.0, 0.0);
    }

    /// Forgets what happened this frame: call once the frame has used it.
    pub fn end_frame(&mut self) {
        self.pressed = [false; ACTIONS];
        self.released = [false; ACTIONS];
        self.look = (0.0, 0.0);
        self.wheel = 0.0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_tap_between_frames_is_still_a_press() {
        let mut input = Input::new();
        input.key("KeyR", true);
        input.key("KeyR", false);
        assert!(input.pressed(Action::Reload) && !input.held(Action::Reload));
        input.end_frame();
        assert!(!input.pressed(Action::Reload));
    }

    #[test]
    fn opposite_keys_cancel_and_the_mouse_turns() {
        let mut input = Input::new();
        input.key("KeyW", true);
        input.key("KeyD", true);
        input.key("KeyA", true);
        assert_eq!(input.movement(), (0.0, 1.0));
        input.mouse_motion(100.0, -50.0);
        let (left, up) = input.turn(0.016);
        assert!(left < 0.0 && up > 0.0, "right and up: {left} {up}");
    }
}
