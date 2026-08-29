use std::{
    fs::{self, File, OpenOptions},
    io,
    os::fd::AsRawFd,
    path::Path,
};

use tauri::{
    menu::{Menu, MenuItemBuilder, PredefinedMenuItem},
    tray::TrayIconBuilder,
    App, AppHandle, Emitter, Manager, Runtime,
};

const MAIN_WINDOW: &str = "main";
const QUICK_CAPTURE_WINDOW: &str = "quick-capture";
const NAVIGATE_EVENT: &str = "ion:navigate";

const OPEN_ION: &str = "open-ion";
const OPEN_HOME: &str = "open-home";
const OPEN_TODAY: &str = "open-today";
const QUICK_CAPTURE: &str = "quick-capture";
const QUIT_ION: &str = "quit-ion";

pub struct InstanceGuard {
    _file: File,
}

#[derive(Debug, PartialEq, Eq)]
enum TrayAction {
    Open,
    Home,
    Today,
    QuickCapture,
    Quit,
}

impl TrayAction {
    fn from_id(id: &str) -> Option<Self> {
        match id {
            OPEN_ION => Some(Self::Open),
            OPEN_HOME => Some(Self::Home),
            OPEN_TODAY => Some(Self::Today),
            QUICK_CAPTURE => Some(Self::QuickCapture),
            QUIT_ION => Some(Self::Quit),
            _ => None,
        }
    }
}

pub fn acquire_instance_guard(app: &App) -> io::Result<Option<InstanceGuard>> {
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|error| io::Error::other(error.to_string()))?;
    fs::create_dir_all(&app_data)?;
    acquire_lock(&app_data.join("ion-desktop.lock"))
}

fn acquire_lock(path: &Path) -> io::Result<Option<InstanceGuard>> {
    let file = OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .truncate(false)
        .open(path)?;

    // SAFETY: `file` owns this live descriptor for at least as long as the flock call.
    let result = unsafe { flock(file.as_raw_fd(), LOCK_EX | LOCK_NB) };
    if result == 0 {
        return Ok(Some(InstanceGuard { _file: file }));
    }

    let error = io::Error::last_os_error();
    if error.kind() == io::ErrorKind::WouldBlock {
        Ok(None)
    } else {
        Err(error)
    }
}

pub fn setup(app: &App) -> tauri::Result<()> {
    let open = MenuItemBuilder::with_id(OPEN_ION, "Open Ion").build(app)?;
    let home = MenuItemBuilder::with_id(OPEN_HOME, "Home").build(app)?;
    let today = MenuItemBuilder::with_id(OPEN_TODAY, "Today").build(app)?;
    let capture = MenuItemBuilder::with_id(QUICK_CAPTURE, "Quick Capture…").build(app)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItemBuilder::with_id(QUIT_ION, "Quit Ion").build(app)?;
    let menu = Menu::with_items(app, &[&open, &home, &today, &capture, &separator, &quit])?;
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or_else(|| tauri::Error::AssetNotFound("default window icon".into()))?;

    TrayIconBuilder::with_id("ion")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("Ion OS")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| {
            if let Some(action) = TrayAction::from_id(event.id().as_ref()) {
                handle_action(app, action);
            }
        })
        .build(app)?;
    Ok(())
}

pub fn hide_window<R: Runtime>(app: &AppHandle<R>, label: &str) {
    if let Some(window) = app.get_webview_window(label) {
        let _ = window.hide();
    }
}

pub fn show_main<R: Runtime>(app: &AppHandle<R>) {
    show_and_focus(app, MAIN_WINDOW, false);
}

fn show_and_focus<R: Runtime>(app: &AppHandle<R>, label: &str, center: bool) {
    if let Some(window) = app.get_webview_window(label) {
        let _ = window.unminimize();
        if center {
            let _ = window.center();
        }
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn handle_action<R: Runtime>(app: &AppHandle<R>, action: TrayAction) {
    match action {
        TrayAction::Open => show_main(app),
        TrayAction::Home => navigate(app, "home"),
        TrayAction::Today => navigate(app, "today"),
        TrayAction::QuickCapture => show_and_focus(app, QUICK_CAPTURE_WINDOW, true),
        TrayAction::Quit => app.exit(0),
    }
}

fn navigate<R: Runtime>(app: &AppHandle<R>, workspace: &'static str) {
    show_main(app);
    let _ = app.emit_to(MAIN_WINDOW, NAVIGATE_EVENT, workspace);
}

const LOCK_EX: i32 = 2;
const LOCK_NB: i32 = 4;

extern "C" {
    fn flock(fd: i32, operation: i32) -> i32;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tray_ids_map_only_to_fixed_actions() {
        assert_eq!(TrayAction::from_id(OPEN_HOME), Some(TrayAction::Home));
        assert_eq!(TrayAction::from_id(OPEN_TODAY), Some(TrayAction::Today));
        assert_eq!(TrayAction::from_id("arbitrary"), None);
    }

    #[test]
    fn process_lock_allows_only_one_live_guard() {
        let path = std::env::temp_dir().join(format!(
            "ion-desktop-instance-{}-{}.lock",
            std::process::id(),
            std::thread::current().name().unwrap_or("test")
        ));
        let first = acquire_lock(&path).expect("first lock should succeed");
        assert!(first.is_some());
        assert!(acquire_lock(&path)
            .expect("contended lock should be readable")
            .is_none());
        drop(first);
        assert!(acquire_lock(&path)
            .expect("released lock should be reusable")
            .is_some());
        let _ = fs::remove_file(path);
    }
}
