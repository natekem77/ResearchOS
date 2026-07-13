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
      switch call.method {
      case "readImageClipboard":
        self.readImageClipboard(result: result)
      case "readRichClipboard":
        self.readRichClipboard(result: result)
      case "writeTableClipboard":
        self.writeTableClipboard(call: call, result: result)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func readRichClipboard(result: @escaping FlutterResult) {
    let pasteboard = UIPasteboard.general
    let providers = pasteboard.itemProviders
    let typeIdentifiers = providers.first?.registeredTypeIdentifiers.sorted() ?? []
    let richTypes = [
      "com.mundi.notebook-table+json",
      "public.html",
      "public.rtf",
      "com.apple.flat-rtfd",
      "public.tab-separated-values-text",
      "public.utf8-plain-text",
      "public.plain-text",
      "public.text"
    ]
    loadFirstRichClipboardText(
      providers: providers,
      richTypes: richTypes,
      providerIndex: 0,
      typeIndex: 0,
      typeIdentifiers: typeIdentifiers,
      result: result
    )
  }

  private func loadFirstRichClipboardText(
    providers: [NSItemProvider],
    richTypes: [String],
    providerIndex: Int,
    typeIndex: Int,
    typeIdentifiers: [String],
    result: @escaping FlutterResult
  ) {
    if typeIndex >= richTypes.count {
      result([
        "type_identifiers": typeIdentifiers,
        "selected_representation": "unsupported"
      ])
      debugClipboardSelection(typeIdentifiers: typeIdentifiers, selectedRepresentation: "rich:unsupported")
      return
    }
    if providerIndex >= providers.count {
      loadFirstRichClipboardText(
        providers: providers,
        richTypes: richTypes,
        providerIndex: 0,
        typeIndex: typeIndex + 1,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    let provider = providers[providerIndex]
    let typeIdentifier = richTypes[typeIndex]
    guard provider.hasItemConformingToTypeIdentifier(typeIdentifier) else {
      loadFirstRichClipboardText(
        providers: providers,
        richTypes: richTypes,
        providerIndex: providerIndex + 1,
        typeIndex: typeIndex,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, _ in
      DispatchQueue.main.async {
        guard let data = data, !data.isEmpty else {
          self.loadFirstRichClipboardText(
            providers: providers,
            richTypes: richTypes,
            providerIndex: providerIndex + 1,
            typeIndex: typeIndex,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
          return
        }
        let isRichText = typeIdentifier == "public.rtf" || typeIdentifier == "com.apple.flat-rtfd"
        let encoding: String.Encoding = isRichText ? .ascii : .utf8
        guard let text = String(data: data, encoding: encoding) ??
          String(data: data, encoding: .utf8) ??
          String(data: data, encoding: .ascii) else {
          self.loadFirstRichClipboardText(
            providers: providers,
            richTypes: richTypes,
            providerIndex: providerIndex + 1,
            typeIndex: typeIndex,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
          return
        }
        self.debugClipboardSelection(
          typeIdentifiers: typeIdentifiers,
          selectedRepresentation: "rich:\(typeIdentifier)"
        )
        var payload: [String: Any] = [
          "type_identifiers": typeIdentifiers,
          "selected_representation": typeIdentifier
        ]
        if typeIdentifier == "com.mundi.notebook-table+json" {
          payload["mundi_json"] = text
        } else if typeIdentifier == "public.html" {
          payload["html"] = text
        } else if isRichText {
          if let html = self.htmlFromRichTextData(data, typeIdentifier: typeIdentifier) {
            payload["html"] = html
          } else {
            payload["rtf"] = text
          }
        } else if typeIdentifier == "public.tab-separated-values-text" {
          payload["tsv"] = text
        } else {
          payload["text"] = text
        }
        result(payload)
      }
    }
  }

  private func htmlFromRichTextData(_ data: Data, typeIdentifier: String) -> String? {
    let documentType: NSAttributedString.DocumentType =
      typeIdentifier == "public.rtf" ? .rtf : .rtfd
    var readAttributes: NSDictionary?
    guard let attributed = try? NSAttributedString(
      data: data,
      options: [.documentType: documentType],
      documentAttributes: &readAttributes
    ) else {
      return nil
    }
    let range = NSRange(location: 0, length: attributed.length)
    guard let htmlData = try? attributed.data(
      from: range,
      documentAttributes: [.documentType: NSAttributedString.DocumentType.html]
    ) else {
      return nil
    }
    return String(data: htmlData, encoding: .utf8)
  }

  private func writeTableClipboard(call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: Any] else {
      result(FlutterError(code: "bad_args", message: "Missing table clipboard payload", details: nil))
      return
    }
    var item: [String: Any] = [:]
    if let mundiJson = args["mundi_json"] as? String, !mundiJson.isEmpty {
      item["com.mundi.notebook-table+json"] = mundiJson
    }
    if let html = args["html"] as? String, !html.isEmpty {
      item["public.html"] = html
    }
    if let tsv = args["tsv"] as? String, !tsv.isEmpty {
      item["public.tab-separated-values-text"] = tsv
    }
    if let text = args["text"] as? String, !text.isEmpty {
      item["public.utf8-plain-text"] = text
      item["public.text"] = text
    }
    UIPasteboard.general.items = [item]
    result(nil)
  }

  private func readImageClipboard(result: @escaping FlutterResult) {
    let pasteboard = UIPasteboard.general
    let providers = pasteboard.itemProviders
    let typeIdentifiers = providers.first?.registeredTypeIdentifiers.sorted() ?? []
    let imageTypes = [
      "public.png",
      "public.jpeg",
      "public.heic",
      "public.heif",
      "public.tiff",
      "public.webp",
      "org.webmproject.webp"
    ]

    loadFirstUIImage(
      providers: providers,
      providerIndex: 0,
      typeIdentifiers: typeIdentifiers,
      imageTypes: imageTypes,
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
      loadFirstImageFileUrl(
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
          self.returnClipboardImage(
            result: result,
            typeIdentifiers: typeIdentifiers,
            selectedRepresentation: typeIdentifier,
            mimeType: self.mimeType(for: typeIdentifier),
            fileExtension: self.fileExtension(for: typeIdentifier),
            bytes: data
          )
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
    imageTypes: [String],
    result: @escaping FlutterResult
  ) {
    if providerIndex >= providers.count {
      loadFirstImageData(
        providers: providers,
        imageTypes: imageTypes,
        providerIndex: 0,
        typeIndex: 0,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }
    let provider = providers[providerIndex]
    guard provider.canLoadObject(ofClass: UIImage.self) else {
      loadFirstUIImage(
        providers: providers,
        providerIndex: providerIndex + 1,
        typeIdentifiers: typeIdentifiers,
        imageTypes: imageTypes,
        result: result
      )
      return
    }
    provider.loadObject(ofClass: UIImage.self) { object, _ in
      DispatchQueue.main.async {
        if let image = object as? UIImage, let data = image.pngData(), !data.isEmpty {
          self.returnClipboardImage(
            result: result,
            typeIdentifiers: typeIdentifiers,
            selectedRepresentation: "UIImage",
            mimeType: "image/png",
            fileExtension: ".png",
            bytes: data
          )
        } else {
          self.loadFirstUIImage(
            providers: providers,
            providerIndex: providerIndex + 1,
            typeIdentifiers: typeIdentifiers,
            imageTypes: imageTypes,
            result: result
          )
        }
      }
    }
  }

  private func loadFirstImageFileUrl(
    providers: [NSItemProvider],
    providerIndex: Int,
    typeIdentifiers: [String],
    result: @escaping FlutterResult
  ) {
    if providerIndex >= providers.count {
      loadFirstImageText(
        providers: providers,
        textTypes: [
          "public.html",
          "public.url",
          "public.utf8-plain-text",
          "public.plain-text",
          "public.text"
        ],
        providerIndex: 0,
        typeIndex: 0,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    let provider = providers[providerIndex]
    guard provider.hasItemConformingToTypeIdentifier("public.file-url") else {
      loadFirstImageFileUrl(
        providers: providers,
        providerIndex: providerIndex + 1,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    provider.loadDataRepresentation(forTypeIdentifier: "public.file-url") { data, _ in
      DispatchQueue.main.async {
        if let data = data,
           let text = String(data: data, encoding: .utf8),
           let url = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
           url.isFileURL,
           let fileData = try? Data(contentsOf: url),
           !fileData.isEmpty,
           let mimeType = self.mimeType(forImageUrl: url) {
          self.returnClipboardImage(
            result: result,
            typeIdentifiers: typeIdentifiers,
            selectedRepresentation: "public.file-url",
            mimeType: mimeType,
            fileExtension: self.fileExtension(forMimeType: mimeType),
            bytes: fileData
          )
        } else {
          self.loadFirstImageFileUrl(
            providers: providers,
            providerIndex: providerIndex + 1,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
        }
      }
    }
  }

  private func loadFirstImageText(
    providers: [NSItemProvider],
    textTypes: [String],
    providerIndex: Int,
    typeIndex: Int,
    typeIdentifiers: [String],
    result: @escaping FlutterResult
  ) {
    if typeIndex >= textTypes.count {
      result([
        "type_identifiers": typeIdentifiers,
        "selected_representation": "unsupported"
      ])
      debugClipboardSelection(typeIdentifiers: typeIdentifiers, selectedRepresentation: "unsupported")
      return
    }
    if providerIndex >= providers.count {
      loadFirstImageText(
        providers: providers,
        textTypes: textTypes,
        providerIndex: 0,
        typeIndex: typeIndex + 1,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    let provider = providers[providerIndex]
    let typeIdentifier = textTypes[typeIndex]
    guard provider.hasItemConformingToTypeIdentifier(typeIdentifier) else {
      loadFirstImageText(
        providers: providers,
        textTypes: textTypes,
        providerIndex: providerIndex + 1,
        typeIndex: typeIndex,
        typeIdentifiers: typeIdentifiers,
        result: result
      )
      return
    }

    provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, _ in
      DispatchQueue.main.async {
        guard let data = data,
              let text = String(data: data, encoding: .utf8) else {
          self.loadFirstImageText(
            providers: providers,
            textTypes: textTypes,
            providerIndex: providerIndex + 1,
            typeIndex: typeIndex,
            typeIdentifiers: typeIdentifiers,
            result: result
          )
          return
        }

        if let decoded = self.decodeDataImage(from: text) {
          self.returnClipboardImage(
            result: result,
            typeIdentifiers: typeIdentifiers,
            selectedRepresentation: "\(typeIdentifier):data-image",
            mimeType: decoded.mimeType,
            fileExtension: self.fileExtension(forMimeType: decoded.mimeType),
            bytes: decoded.data
          )
          return
        }

        if let imageSource = self.extractHtmlImageSource(from: text) {
          if let decoded = self.decodeDataImage(from: imageSource) {
            self.returnClipboardImage(
              result: result,
              typeIdentifiers: typeIdentifiers,
              selectedRepresentation: "\(typeIdentifier):html-data-image",
              mimeType: decoded.mimeType,
              fileExtension: self.fileExtension(forMimeType: decoded.mimeType),
              bytes: decoded.data
            )
            return
          }
          if let url = URL(string: imageSource), url.scheme == "https" {
            self.downloadRemoteImage(
              url: url,
              selectedRepresentation: "\(typeIdentifier):html-img",
              typeIdentifiers: typeIdentifiers,
              result: result,
              fallback: {
                self.loadFirstImageText(
                  providers: providers,
                  textTypes: textTypes,
                  providerIndex: providerIndex + 1,
                  typeIndex: typeIndex,
                  typeIdentifiers: typeIdentifiers,
                  result: result
                )
              }
            )
            return
          }
        }

        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: trimmed), url.scheme == "https", self.isLikelyDirectImageUrl(url) {
          self.downloadRemoteImage(
            url: url,
            selectedRepresentation: "\(typeIdentifier):direct-image-url",
            typeIdentifiers: typeIdentifiers,
            result: result,
            fallback: {
              self.loadFirstImageText(
                providers: providers,
                textTypes: textTypes,
                providerIndex: providerIndex + 1,
                typeIndex: typeIndex,
                typeIdentifiers: typeIdentifiers,
                result: result
              )
            }
          )
          return
        }

        self.loadFirstImageText(
          providers: providers,
          textTypes: textTypes,
          providerIndex: providerIndex + 1,
          typeIndex: typeIndex,
          typeIdentifiers: typeIdentifiers,
          result: result
        )
      }
    }
  }

  private func decodeDataImage(from text: String) -> (mimeType: String, data: Data)? {
    guard let start = text.range(of: "data:image/", options: [.caseInsensitive]) else {
      return nil
    }
    let remainder = text[start.lowerBound...]
    guard let comma = remainder.firstIndex(of: ",") else {
      return nil
    }
    let header = String(remainder[..<comma]).lowercased()
    guard header.contains(";base64") else {
      return nil
    }
    let mimeType = header
      .replacingOccurrences(of: "data:", with: "")
      .replacingOccurrences(of: ";base64", with: "")
      .replacingOccurrences(of: "image/jpg", with: "image/jpeg")
    guard allowedDataImageMimeTypes.contains(mimeType) else {
      return nil
    }
    let afterComma = remainder.index(after: comma)
    let base64Prefix = remainder[afterComma...].prefix { character in
      character.isLetter || character.isNumber || character == "+" || character == "/" || character == "="
    }
    guard base64Prefix.count <= 70 * 1024 * 1024,
          let data = Data(base64Encoded: String(base64Prefix), options: [.ignoreUnknownCharacters]),
          !data.isEmpty else {
      return nil
    }
    return (mimeType, data)
  }

  private var allowedDataImageMimeTypes: Set<String> {
    return [
      "image/png",
      "image/jpeg",
      "image/heic",
      "image/heif",
      "image/tiff",
      "image/webp"
    ]
  }

  private func returnClipboardImage(
    result: @escaping FlutterResult,
    typeIdentifiers: [String],
    selectedRepresentation: String,
    mimeType: String,
    fileExtension: String,
    bytes: Data
  ) {
    debugClipboardSelection(
      typeIdentifiers: typeIdentifiers,
      selectedRepresentation: selectedRepresentation
    )
    result([
      "type_identifiers": typeIdentifiers,
      "selected_representation": selectedRepresentation,
      "mime_type": mimeType,
      "file_extension": fileExtension,
      "suggested_filename": "pasted-image-\(Int(Date().timeIntervalSince1970 * 1000))\(fileExtension)",
      "bytes": FlutterStandardTypedData(bytes: bytes)
    ])
  }

  private func debugClipboardSelection(
    typeIdentifiers: [String],
    selectedRepresentation: String
  ) {
    #if DEBUG
    print(
      "mundi_clipboard type_identifiers=\(typeIdentifiers.joined(separator: ",")) selected_representation=\(selectedRepresentation)"
    )
    #endif
  }

  private func extractHtmlImageSource(from text: String) -> String? {
    guard let imgRange = text.range(of: "<img", options: [.caseInsensitive]) else {
      return nil
    }
    let remainder = text[imgRange.lowerBound...]
    guard let srcRange = remainder.range(of: "src", options: [.caseInsensitive]) else {
      return nil
    }
    let afterSrc = remainder[srcRange.upperBound...]
    guard let equals = afterSrc.firstIndex(of: "=") else {
      return nil
    }
    var value = afterSrc[afterSrc.index(after: equals)...]
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty else {
      return nil
    }
    let quote = value.first
    if quote == "\"" || quote == "'" {
      value.removeFirst()
      guard let end = value.firstIndex(of: quote!) else {
        return nil
      }
      return String(value[..<end])
    }
    let end = value.firstIndex { character in
      character.isWhitespace || character == ">"
    } ?? value.endIndex
    return String(value[..<end])
  }

  private func downloadRemoteImage(
    url: URL,
    selectedRepresentation: String,
    typeIdentifiers: [String],
    result: @escaping FlutterResult,
    fallback: @escaping () -> Void
  ) {
    guard url.scheme == "https" else {
      fallback()
      return
    }
    var request = URLRequest(url: url)
    request.timeoutInterval = 12
    URLSession.shared.dataTask(with: request) { data, response, _ in
      DispatchQueue.main.async {
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode),
              http.url?.scheme == "https",
              let data = data,
              !data.isEmpty,
              data.count <= 25 * 1024 * 1024 else {
          fallback()
          return
        }
        let responseMime = http.mimeType?.lowercased()
        let urlMime = self.mimeType(forImageUrl: http.url ?? url)
        let resolvedMimeType = self.allowedDataImageMimeTypes.contains(responseMime ?? "")
          ? responseMime
          : urlMime
        guard let resolvedMimeType = resolvedMimeType,
              self.allowedDataImageMimeTypes.contains(resolvedMimeType) else {
          fallback()
          return
        }
        self.returnClipboardImage(
          result: result,
          typeIdentifiers: typeIdentifiers,
          selectedRepresentation: selectedRepresentation,
          mimeType: resolvedMimeType,
          fileExtension: self.fileExtension(forMimeType: resolvedMimeType),
          bytes: data
        )
      }
    }.resume()
  }

  private func isLikelyDirectImageUrl(_ url: URL) -> Bool {
    return mimeType(forImageUrl: url) != nil
  }

  private func mimeType(forImageUrl url: URL) -> String? {
    switch url.pathExtension.lowercased() {
    case "png":
      return "image/png"
    case "jpg", "jpeg":
      return "image/jpeg"
    case "heic":
      return "image/heic"
    case "heif":
      return "image/heif"
    case "tif", "tiff":
      return "image/tiff"
    case "webp":
      return "image/webp"
    default:
      return nil
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
    case "public.webp", "org.webmproject.webp":
      return "image/webp"
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
    case "public.webp", "org.webmproject.webp":
      return ".webp"
    default:
      return ".png"
    }
  }

  private func fileExtension(forMimeType mimeType: String) -> String {
    switch mimeType {
    case "image/jpeg":
      return ".jpg"
    case "image/heic":
      return ".heic"
    case "image/heif":
      return ".heif"
    case "image/tiff":
      return ".tiff"
    case "image/webp":
      return ".webp"
    default:
      return ".png"
    }
  }
}
