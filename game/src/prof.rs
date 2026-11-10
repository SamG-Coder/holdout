//! Rough timings of the game's own work, for the desktop build's summary: where the
//! milliseconds of a frame go. On the web these cost nothing and report nothing.

#[cfg(not(target_arch = "wasm32"))]
mod clock {
    use std::cell::RefCell;
    use std::collections::BTreeMap;
    use std::time::Instant;

    thread_local! {
        static TOTALS: RefCell<BTreeMap<&'static str, (f64, u64, f64)>> = RefCell::default();
    }

    /// Times from where it is made to where it is dropped, under a name.
    pub struct Scope(&'static str, Instant);

    pub fn scope(name: &'static str) -> Scope {
        Scope(name, Instant::now())
    }

    impl Drop for Scope {
        fn drop(&mut self) {
            let ms = self.1.elapsed().as_secs_f64() * 1000.0;
            TOTALS.with(|totals| {
                let mut totals = totals.borrow_mut();
                let entry = totals.entry(self.0).or_default();
                entry.0 += ms;
                entry.1 += 1;
                entry.2 = entry.2.max(ms);
            });
        }
    }

    /// One line for each name: its total, how many times, and the longest.
    pub fn report() -> Vec<String> {
        TOTALS.with(|totals| {
            totals
                .borrow()
                .iter()
                .map(|(name, (total, count, worst))| {
                    format!("{name}: {total:.0} ms in {count} ({worst:.2} ms at worst)")
                })
                .collect()
        })
    }
}

#[cfg(target_arch = "wasm32")]
mod clock {
    pub struct Scope;

    pub fn scope(_name: &'static str) -> Scope {
        Scope
    }

    pub fn report() -> Vec<String> {
        Vec::new()
    }
}

pub use clock::{report, scope, Scope};
