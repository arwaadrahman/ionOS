mod organizer;
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
            service::set_task_relationships,
            organizer::list_areas,
            organizer::get_area,
            organizer::create_area,
            organizer::update_area,
            organizer::archive_area,
            organizer::unarchive_area,
            organizer::trash_area,
            organizer::restore_area,
            organizer::list_goals,
            organizer::get_goal_detail,
            organizer::create_goal,
            organizer::update_goal,
            organizer::set_goal_state,
            organizer::set_goal_area,
            organizer::archive_goal,
            organizer::unarchive_goal,
            organizer::trash_goal,
            organizer::restore_goal,
            organizer::create_goal_milestone,
            organizer::update_goal_milestone,
            organizer::set_goal_milestone_state,
            organizer::reorder_goal_milestones,
            organizer::trash_goal_milestone,
            organizer::restore_goal_milestone,
            organizer::list_goal_milestones,
            organizer::list_projects,
            organizer::get_project_detail,
            organizer::create_project,
            organizer::update_project,
            organizer::set_project_state,
            organizer::set_project_goal,
            organizer::archive_project,
            organizer::unarchive_project,
            organizer::trash_project,
            organizer::restore_project,
            organizer::create_project_milestone,
            organizer::update_project_milestone,
            organizer::set_project_milestone_state,
            organizer::reorder_project_milestones,
            organizer::trash_project_milestone,
            organizer::restore_project_milestone,
            organizer::list_project_milestones,
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
