# Tools

## sb_info

[sb_info](https://github.com/RustyDust/sb_info) reads everything the local API
of a SonnenBatterie reveals (API v1 and v2, plus the cascade information the
battery's web dashboard uses) and writes it as one JSON report. It only reads;
it never changes anything on the battery.

When reporting a problem with the integration, a report from this tool helps a
lot, especially for setups the integration doesn't handle yet (e.g. cascades
of several batteries or PV strings).

1. Download the version for your operating system from the
   [Releases](https://github.com/RustyDust/sb_info/releases) page (v0.4.0 or
   later) and unpack it.
2. Run it in a terminal, with the IP address of your battery and the password
   of the `User` account:

   ```bash
   SB_PASSWORD=<password> ./sb_info -h <ip address> > report.json
   ```

   On Windows (PowerShell): `$env:SB_PASSWORD="<password>"; .\sb_info.exe -h <ip address> > report.json`
3. Attach `report.json` to the GitHub issue.

The password is never written to the report and the API token is always
redacted; IP and MAC addresses are redacted by default as well. The serial
number is kept, as it's needed to analyse cascades.

See the [sb_info README](https://github.com/RustyDust/sb_info#readme) for all
options and the report format.
