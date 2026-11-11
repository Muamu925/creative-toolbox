import AppKit

enum NativeStyle {
    static func symbol(_ name: String, size: CGFloat = 18, color: NSColor = .secondaryLabelColor) -> NSImageView {
        let image = NSImageView()
        image.image = NSImage(systemSymbolName: name, accessibilityDescription: nil)?
            .withSymbolConfiguration(.init(pointSize: size, weight: .medium))
        image.contentTintColor = color
        image.widthAnchor.constraint(equalToConstant: size + 4).isActive = true
        image.heightAnchor.constraint(equalToConstant: size + 4).isActive = true
        return image
    }
    static func column(_ views: [NSView], spacing: CGFloat = 6) -> NSStackView {
        let stack = NSStackView()
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = spacing
        stack.detachesHiddenViews = false
        for view in views { stack.addArrangedSubview(view); stack.setVisibilityPriority(.mustHold, for: view) }
        return stack
    }
    static func card(_ contents: NSStackView, inset: CGFloat = 14) -> NSBox {
        let card = NSBox()
        card.boxType = .custom; card.titlePosition = .noTitle
        card.cornerRadius = 12; card.borderWidth = 0.5
        card.borderColor = .separatorColor; card.fillColor = .controlBackgroundColor
        card.contentViewMargins = .zero
        contents.translatesAutoresizingMaskIntoConstraints = false
        card.contentView!.addSubview(contents)
        NSLayoutConstraint.activate([
            contents.leadingAnchor.constraint(equalTo: card.contentView!.leadingAnchor, constant: inset),
            contents.trailingAnchor.constraint(equalTo: card.contentView!.trailingAnchor, constant: -inset),
            contents.topAnchor.constraint(equalTo: card.contentView!.topAnchor, constant: inset),
            contents.bottomAnchor.constraint(equalTo: card.contentView!.bottomAnchor, constant: -inset)
        ])
        return card
    }
    static func separator() -> NSBox { let line = NSBox(); line.boxType = .separator; return line }
}
