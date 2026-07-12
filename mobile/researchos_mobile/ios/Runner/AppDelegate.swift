import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    registerClipboardChannel()
    return launched
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }

  private func registerClipboardChannel() {
    guard let controller = window?.rootViewController as? FlutterViewController else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "mundi/clipboard",
      binaryMessenger: controller.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "readImageClipboard" else {
        result(FlutterMethodNotImplemented)
        return
      }
      self.readImageClipboard(result: result)
    }
  }

  private func readImageClipboard(result: @escaping FlutterResult) {
    let pasteboard = UIPasteboard.general
    let providers = pasteboard.itemProviders
    let typeIdentifiers = Array(Set(providers.flatMap { $0.registeredTypeIdentifiers })).sorted()
    let imageTypes = [
      "public.png",
      "public.jpeg",
      "public.heic",
      "public.heif",
      "public.tiff",
      "public.image"
    ]

    loadFirstImageData(
      providers: providers,
      imageTypes: imageTypes,
      providerIndex: 0,
      typeIndex: 0,
      typeIdentifiers: typeIdentifiers,
      result: result
    )
  }

  private func loadFirstImageData(
    providers: [NSItemProvider],
    imageTypes: [String],
    providerIndex: Int,
    typeIndex: Int,
    typeIdentifiers: [String],
    result: @escaping FlutterResult
  ) {
    if typeIndex >= imageTypes.count {
      loadFirstUIImage(
        providers: providers,
        providerIndex: 0,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }
    if providerIndex >= providers.count {
      loadFirstImageData(
        providers: providers,
        imageTypes: imageTypes,
        providerIndex: 0,
        typeIndex: typeIndex + 1,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    let provider = providers[providerIndex]
    let typeIdentifier = imageTypes[typeIndex]
    guard provider.hasItemConformingToTypeIdentifier(typeIdentifier) else {
      loadFirstImageData(
        providers: providers,
        imageTypes: imageTypes,
        providerIndex: providerIndex + 1,
        typeIndex: typeIndex,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, _ in
      DispatchQueue.main.async {
        if let data = data, !data.isEmpty {
          result([
            "type_identifiers": typeIdentifiers,
            "selected_representation": typeIdentifier,
            "mime_type": self.mimeType(for: typeIdentifier),
            "file_extension": self.fileExtension(for: typeIdentifier),
            "bytes": FlutterStandardTypedData(bytes: data)
          ])
        } else {
          self.loadFirstImageData(
            providers: providers,
            imageTypes: imageTypes,
            providerIndex: providerIndex + 1,
            typeIndex: typeIndex,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
        }
      }
    }
  }

  private func loadFirstUIImage(
    providers: [NSItemProvider],
    providerIndex: Int,
    typeIdentifiers: [String],
    result: @escaping FlutterResult
  ) {
    if providerIndex >= providers.count {
      result([
        "type_identifiers": typeIdentifiers,
        "selected_representation": "unsupported"
      ])
      return
    }
    let provider = providers[providerIndex]
    guard provider.canLoadObject(ofClass: UIImage.self) else {
      loadFirstUIImage(
        providers: providers,
        providerIndex: providerIndex + 1,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }
    provider.loadObject(ofClass: UIImage.self) { object, _ in
      DispatchQueue.main.async {
        if let image = object as? UIImage, let data = image.pngData(), !data.isEmpty {
          result([
            "type_identifiers": typeIdentifiers,
            "selected_representation": "UIImage",
            "mime_type": "image/png",
            "file_extension": ".png",
            "bytes": FlutterStandardTypedData(bytes: data)
          ])
        } else {
          self.loadFirstUIImage(
            providers: providers,
            providerIndex: providerIndex + 1,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
        }
      }
    }
  }

  private func mimeType(for typeIdentifier: String) -> String {
    switch typeIdentifier {
    case "public.jpeg":
      return "image/jpeg"
    case "public.heic":
      return "image/heic"
    case "public.heif":
      return "image/heif"
    case "public.tiff":
      return "image/tiff"
    default:
      return "image/png"
    }
  }

  private func fileExtension(for typeIdentifier: String) -> String {
    switch typeIdentifier {
    case "public.jpeg":
      return ".jpg"
    case "public.heic":
      return ".heic"
    case "public.heif":
      return ".heif"
    case "public.tiff":
      return ".tiff"
    default:
      return ".png"
    }
  }
}
