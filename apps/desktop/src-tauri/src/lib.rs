mod service;

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(service::ServiceState::default())
        .invoke_handler(tauri::generate_handler![
            service::service_health,
            service::list_tasks,
            service::list_trashed_tasks,
            service::create_task,
            service::update_task,
            service::complete_task,
            service::reopen_task,
            service::trash_task,
            service::restore_task,
        ])
        .setup(|app| {
            if !cfg!(debug_assertions) {
                service::start_nonfatal(app.handle());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Ion desktop application");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
            service::request_shutdown(app);
        }
    });
}
