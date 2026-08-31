mod desktop;
mod google_calendar;
mod home;
mod organizer;
mod service;
mod today;

use tauri::Manager;

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(service::ServiceState::default())
        .manage(google_calendar::GoogleState::default())
        .invoke_handler(tauri::generate_handler![
            google_calendar::get_google_calendar_status,
            google_calendar::connect_google_calendar,
            google_calendar::set_google_calendar_enabled,
            google_calendar::set_google_calendar_hidden,
            google_calendar::set_calendar_block_category,
            google_calendar::sync_google_calendars,
            google_calendar::disconnect_google_calendar,
            home::get_home,
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
            organizer::get_recovery,
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
            today::get_today,
            today::add_task_to_today,
            today::remove_task_from_today,
            today::set_today_role,
            today::reorder_today_tasks,
        ])
        .setup(|app| {
            let Some(instance_guard) = desktop::acquire_instance_guard(app)? else {
                app.handle().exit(0);
                return Ok(());
            };
            app.manage(instance_guard);
            desktop::setup(app)?;
            if !cfg!(debug_assertions) {
                service::start_nonfatal(app.handle());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Ion desktop application");
    app.run(|app, event| match event {
        tauri::RunEvent::ExitRequested { .. } => service::request_shutdown(app),
        tauri::RunEvent::WindowEvent {
            label,
            event: tauri::WindowEvent::CloseRequested { api, .. },
            ..
        } if label == "main" || label == "quick-capture" => {
            api.prevent_close();
            desktop::hide_window(app, &label);
        }
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen { .. } => desktop::show_main(app),
        _ => {}
    });
}
