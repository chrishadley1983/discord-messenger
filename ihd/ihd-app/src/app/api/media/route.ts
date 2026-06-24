import { NextRequest, NextResponse } from "next/server";
import { spawn, execSync } from "child_process";

const WAYLAND_ENV: Record<string, string> = {
  WAYLAND_DISPLAY: "wayland-0",
  XDG_RUNTIME_DIR: "/run/user/1000",
};

const OVERLAY_LAUNCH = "/home/chrishadley1983/media-overlay/launch.sh";

const APPS: Record<string, string> = {
  netflix: "https://www.netflix.com",
  nowtv: "https://www.nowtv.com",
  youtube: "https://www.youtube.com",
};

function runDetached(command: string, args: string[], env?: Record<string, string>) {
  const child = spawn(command, args, {
    detached: true,
    stdio: "ignore",
    env: { ...process.env, ...env },
  });
  child.unref();
}

function killQuiet(pattern: string) {
  try {
    execSync(`pkill -f '${pattern}' || true`, { stdio: "ignore" });
  } catch {
    // ignore
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { action, app } = body;

  try {
    if (action === "launch" && APPS[app]) {
      // Kill any existing media browser + overlay
      killQuiet("chromium.*media-browser");
      killQuiet("close-overlay.py");

      // Build Chromium args
      const url = APPS[app];
      const chromiumArgs = [
        `--app=${url}`,
        "--start-maximized",
        "--user-data-dir=/home/chrishadley1983/.media-browser",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--autoplay-policy=no-user-gesture-required",
        "--ozone-platform=wayland",
      ];

      if (app === "youtube") {
        chromiumArgs.push(
          "--user-agent=Mozilla/5.0 (SMART-TV; Linux; Tizen 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        );
      }

      // Launch Chromium detached
      runDetached("chromium", chromiumArgs, WAYLAND_ENV);

      // Launch the floating close overlay button
      runDetached("bash", [OVERLAY_LAUNCH]);

      return NextResponse.json({ ok: true, launched: app });
    }

    if (action === "close") {
      killQuiet("chromium.*media-browser");
      killQuiet("close-overlay.py");
      return NextResponse.json({ ok: true, closed: true });
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (e) {
    return NextResponse.json(
      { error: "Media control failed", detail: String(e) },
      { status: 200 }
    );
  }
}
