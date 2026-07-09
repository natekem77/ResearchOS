# iPhone Testing

This guide explains how to test the ResearchOS Flutter mobile preview on iPhone/iOS against the FastAPI backend.

## Mac Setup

Install:

- macOS with current Xcode support
- Xcode from the Mac App Store
- Flutter SDK
- CocoaPods

Check Flutter:

```bash
flutter doctor
flutter doctor --verbose
```

Accept Xcode licenses:

```bash
sudo xcodebuild -license accept
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
```

Install iOS dependencies:

```bash
sudo gem install cocoapods
```

## Flutter iOS Setup

From the repo:

```bash
cd mobile/researchos_mobile
flutter pub get
flutter doctor
```

If the iOS folder has not been generated yet:

```bash
flutter create .
flutter pub get
```

## iPhone Simulator

Start the backend:

```bash
cd /path/to/labnote-ai
./scripts/demo.sh
```

Run the app:

```bash
cd mobile/researchos_mobile
flutter run -d "iPhone 15"
```

For iOS Simulator, `http://127.0.0.1:8001` usually works because the simulator runs on the Mac and can reach the Mac loopback interface.

## Physical iPhone Testing

A physical iPhone cannot use `127.0.0.1` to reach the Mac. On the iPhone, `127.0.0.1` means the iPhone itself.

Use one of:

- LAN URL: `http://<mac-lan-ip>:8001`
- Tailscale URL: `http://<tailscale-ip>:8001` or HTTPS if configured
- Lab server URL: `https://researchos.example.edu`

Run the backend on a reachable host:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<mac-lan-ip>:8001 ./scripts/run_server.sh
```

Or for dev scripts:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<mac-lan-ip>:8001 ./scripts/demo.sh
```

Find the Mac LAN IP:

```bash
ipconfig getifaddr en0
```

Open on the iPhone Safari first:

```text
http://<mac-lan-ip>:8001/health
```

Expected:

```json
{"status":"ok","project":"ResearchOS"}
```

Then enter the same base URL in the app Server Connection screen.

## Trusted Developer Profile

For a physical iPhone build:

1. Open `mobile/researchos_mobile/ios/Runner.xcworkspace` in Xcode.
2. Select the Runner target.
3. Set a development team under Signing & Capabilities.
4. Build to the connected iPhone.
5. On iPhone, go to Settings → General → VPN & Device Management.
6. Trust the developer profile.

## Server Settings Screen

The app includes:

- first-launch Server Connection screen
- Server Settings in Settings
- Test Connection button
- local persistence of the selected backend URL

Use this to switch between local simulator, LAN, Tailscale, or lab-server URLs.

## Common Errors

`Connection refused`

- Backend is not running.
- Wrong port.
- Firewall blocks inbound connections.

`127.0.0.1 works on Mac but not iPhone`

- Expected behavior. Use Mac LAN IP or Tailscale URL.

`SocketException: Failed host lookup`

- DNS name is not reachable from the phone.
- VPN/Tailscale not connected.

`App installs but will not open`

- Trust the developer profile on the iPhone.
- Check Xcode signing team.

`Cleartext HTTP blocked`

- iOS can restrict plain HTTP depending on generated project settings.
- For production-like testing, use HTTPS.
- For local development, configure iOS app transport security in the generated iOS project if needed.

`OneNote login redirect fails`

- Microsoft redirect URI must match the URL mode.
- Local dev redirect: `http://localhost:8001/auth/callback`
- Lab/mobile mode needs a separately registered redirect URI using the public server URL.
