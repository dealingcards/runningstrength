# Runner Strength

This is a private, installable phone app for the supplied Base Builder, Base Builder V2, and Race Builder plans.

- Your race date and workout completion are stored only in the browser on your phone.
- The app has no account, analytics, or internet data connection.
- Once installed from a secure web address, it works offline.

## Use it privately on a phone

1. Put the contents of this folder on any private HTTPS-enabled web space you control.
2. Open that address on your phone.
3. On iPhone, use Safari's Share menu and choose **Add to Home Screen**. On Android, use the browser's **Install app** option.

For a laptop preview, serve this folder with any simple local web server. The app itself is entirely static; no setup or database is required.

## Updating the source plans

The "build_program_data.py" script rebuilds "programs.js" from the supplied Base Builder Word document, the Base Builder V2 PDFs, and the Race Builder PDFs. The PDF folder paths can be overridden with "BASE_BUILDER_V2_DIR" and "RACE_BUILDER_DIR" if the files move.

It intentionally retains session prescriptions, RPE, tempo, rest, and technique notes, while excluding source dates, weekdays, working weights, and load information.
