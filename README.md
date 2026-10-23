# Test workspace

## Start the app

Run the application from its project directory:

```bash
python app.py
```

The app reads `app_config.json` beside the application (or executable). Its
`ip_address` and `port` values control the server bind address. All configured
paths may be absolute or relative to that same directory:

- `test_path`: Robot Framework test folders.
- `report_path`: generated report folders.
- `log_path`: application log directory (`application.log`).
- `sqlite_db_path`: SQLite run-history database.

Static web assets are loaded from the bundled `static/` directory. Generated
variable files and Robot selection helpers are written to `tmp/` beside the
application.

## Run and find tests

Select the Robot files and test cases in the browser, set any variable values,
and choose **Run selected tests**. Leave the report name blank to use
`<section>_yyyy-mm-dd_hh-mm-ss`.

The backend writes `variables_<report_name>.py` to `tmp/`. Each run's reports
are stored in `<report_path>/<report_name>/` as `<report_name>_report.html`,
`<report_name>_log.html`, and `<report_name>_output.xml`. Robot Framework's
console output is streamed to the run page over a run-specific WebSocket and is
persisted in the configured SQLite database so it remains available after a
browser refresh or server restart.

The **Processes** page at `/tests-status` shows each run, its Robot test
progress, process ID, and console history. Individual runs can be stopped and
finished process history can be deleted without removing its reports. **Kill
all & clear history** stops active runs and deletes all process records but
leaves the report folders intact.

The **Reports** page at `/test-reports` opens each report or log, merges the
selected `output.xml` files into a new report, deletes selected report folders,
and downloads one or more report folders as a ZIP archive. Merging creates a
new report and preserves the source reports.