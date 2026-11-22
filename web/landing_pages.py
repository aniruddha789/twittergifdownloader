from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    title: str
    body: str


@dataclass(frozen=True)
class Faq:
    question: str
    answer: str


@dataclass(frozen=True)
class LandingPage:
    slug: str
    nav_label: str
    h1_pre: str
    h1_highlight: str
    h1_post: str
    page_title: str
    description: str
    eyebrow: str
    lede: str
    specs: tuple[tuple[str, str], ...]
    steps: tuple[Step, ...]
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    faqs: tuple[Faq, ...]
    related: tuple[str, ...]
    tool_button: str = "Get GIF"
    updated: str = "2026-11-22"

    @property
    def title(self) -> str:
        return f"{self.h1_pre}{self.h1_highlight}{self.h1_post}".strip()

    @property
    def path(self) -> str:
        return f"/{self.slug}"


LANDING_PAGES: tuple[LandingPage, ...] = (
    LandingPage(
        slug="twitter-gif-to-mp4",
        nav_label="Twitter GIF to MP4",
        h1_pre="Twitter GIF to ",
        h1_highlight="MP4",
        h1_post=" without re-encoding",
        page_title="Twitter GIF to MP4 - Download the Original X File",
        description=(
            "Turn a Twitter (X) GIF into an MP4 by downloading the exact file X "
            "serves. No re-encoding, no watermark, works on mobile and desktop."
        ),
        eyebrow="Format guide",
        lede=(
            "Every GIF on X is really a short, silent MP4. Paste a post link and "
            "this downloader grabs that MP4 and normalizes it so Android, iPhone, "
            "and WhatsApp can open it, while the picture looks the same as on X."
        ),
        specs=(
            ("What you download", "The MP4 from X's CDN, normalized for phones"),
            ("Video format", "H.264 MP4, silent for GIF posts"),
            ("Audio", "None for animated GIF posts"),
            ("Quality", "Visually unchanged"),
            ("Typical size", "About 0.3 to 5 MB for a short clip"),
            ("Platforms", "iPhone, Android, Windows, macOS"),
        ),
        steps=(
            Step(
                "Copy the post link",
                "Open the post on x.com or in the X app, tap Share, then Copy link. "
                "The post must be public.",
            ),
            Step(
                "Paste the link above",
                "The resolver reads the numeric post ID and asks X's public media "
                "endpoint for the attached MP4.",
            ),
            Step(
                "Choose Download MP4",
                "The download page streams the original file with attachment "
                "headers. GIF conversion is optional.",
            ),
        ),
        sections=(
            (
                "What X actually stores",
                (
                    "When you upload a GIF to X, the platform converts it to an MP4, "
                    "usually H.264 with no audio track. That is why the file you get "
                    "from a downloader is named .mp4 even though the post shows a GIF "
                    "badge.",
                    "The conversion is not a downgrade. X's player was built around "
                    "MP4, which seeks faster and uses far less bandwidth than a "
                    "traditional GIF. The file on the CDN is the same one the player "
                    "uses.",
                ),
            ),
            (
                "Why download the MP4 instead of a GIF",
                (
                    "An MP4 is smaller, sharper, and works in Discord, Slack, "
                    "Telegram, and most editing apps. A real GIF is only useful when "
                    "a site or app refuses to accept video.",
                    "If you need a true .gif, the same download page offers a "
                    "palette-based ffmpeg conversion. Use it as a fallback, not the "
                    "default.",
                ),
            ),
            (
                "What does not work",
                (
                    "Only public posts with animated_gif or video media can be "
                    "resolved. Protected accounts, deleted posts, and posts with only "
                    "photos are rejected before any download starts.",
                    "If X rate-limits the public lookup endpoint, wait a minute and "
                    "try again. The resolver does not use paid API credits.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Why is my Twitter GIF downloading as an MP4?",
                "X converts GIF uploads to MP4 for playback and storage. The "
                "downloader saves that exact file. To get a .gif, use the Convert "
                "button on the download page.",
            ),
            Faq(
                "Does downloading an MP4 reduce quality?",
                "Not noticeably. The MP4 is re-encoded once with a high-quality "
                "H.264 preset so Android Gallery, iOS, and WhatsApp can open it, "
                "and the result looks the same as on X. Converting to GIF is a "
                "separate, more noticeable re-encode.",
            ),
            Faq(
                "Can I download from a private account?",
                "No. The post must be public and its media must still be available.",
            ),
            Faq(
                "Is there a file size limit?",
                "The proxy caps upstream MP4s at the configured MAX_MEDIA_BYTES "
                "value, 30 MB by default. Most GIF clips are far smaller.",
            ),
            Faq(
                "Do I need the bot?",
                "No. Pasting a link is enough. The bot is an optional reply-based "
                "shortcut.",
            ),
            Faq(
                "Can I use the MP4 in a video editor?",
                "Yes. H.264 MP4 imports into most editors. Check the creator's "
                "rights before republishing.",
            ),
        ),
        related=(
            "why-twitter-converts-gifs-to-mp4",
            "save-x-gif-for-discord",
            "download-x-gifs-on-pc",
        ),
    ),
    LandingPage(
        slug="why-twitter-converts-gifs-to-mp4",
        nav_label="Why MP4?",
        h1_pre="Why X turns ",
        h1_highlight="GIFs into MP4",
        h1_post="",
        page_title="Why Twitter Converts GIFs to MP4 (and How to Get a GIF Back)",
        description=(
            "Twitter and X store GIFs as silent MP4 files. Here is why, what "
            "changes, and how to convert one back to a real .gif when you need it."
        ),
        eyebrow="Explainer",
        lede=(
            "If you have ever saved a GIF from X and found an MP4 in your downloads "
            "folder, nothing went wrong. X deliberately stores animated GIFs as "
            "short silent videos."
        ),
        specs=(
            ("Upload format", "GIF, PNG, or short video"),
            ("Stored format", "MP4, usually H.264"),
            ("Audio", "Stripped for GIF uploads"),
            ("Playback", "Looped, muted, autoplay"),
            ("Best download", "Original MP4"),
            ("True GIF", "Optional server conversion"),
        ),
        steps=(
            Step(
                "Paste the post link",
                "Use the box at the top of this page. The resolver finds the post's "
                "animated media without any extra app.",
            ),
            Step(
                "Preview the original MP4",
                "The download page shows the clip and explains which file you are "
                "about to save.",
            ),
            Step(
                "Convert only if you need a .gif",
                "The GIF button re-encodes the MP4 with a generated palette. Use it "
                "when a destination refuses video.",
            ),
        ),
        sections=(
            (
                "The short version",
                (
                    "GIF is a 1987 image format with a 256-color limit per frame. A "
                    "five-second GIF can easily be larger than a full HD video of the "
                    "same length. X converts GIF uploads to MP4 so the timeline loads "
                    "faster and uses less mobile data.",
                    "The GIF badge you see is a label, not the file format. "
                    "Underneath it, X's player is streaming an MP4.",
                ),
            ),
            (
                "What you gain and lose",
                (
                    "You gain smaller files, smoother playback, and better color. You "
                    "lose the .gif extension and universal image handling. Some older "
                    "forums, email clients, and chat tools still only accept image "
                    "files.",
                    "For those places, convert the MP4 back to GIF. The result will be "
                    "larger than the MP4; that is a property of the format, not a bug.",
                ),
            ),
            (
                "Why some GIFs look worse after conversion",
                (
                    "A GIF is limited to 256 colors per frame, so gradients and "
                    "shadows can band. The converter in this app generates a palette "
                    "from the clip and caps width and frame rate to keep the file "
                    "practical.",
                    "If fidelity matters more than compatibility, keep the MP4. If a "
                    "platform requires GIF, convert and accept the trade-off.",
                ),
            ),
            (
                "A note on rights",
                (
                    "Downloading a file does not grant permission to republish it. "
                    "Reaction GIFs and clips often belong to the person who made them. "
                    "Credit or ask before using someone else's media in your own "
                    "project.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Are Twitter GIFs actually videos?",
                "Yes. X stores animated GIFs as silent, looping MP4 files and displays "
                "a GIF badge in the interface.",
            ),
            Faq(
                "Can I get the original .gif file back?",
                "No. The original upload is not kept in its original form. You can "
                "convert the MP4 into a new GIF, but it is a re-encode.",
            ),
            Faq(
                "Why is the converted GIF bigger than the MP4?",
                "GIF stores every frame as a full image with a small color table. It is "
                "far less efficient than video compression.",
            ),
            Faq(
                "Does converting remove the watermark?",
                "No. X does not add a watermark to downloaded media. If the creator "
                "baked one into the clip, it stays.",
            ),
            Faq(
                "Can I convert a long video?",
                "The bot ignores parent media longer than the configured duration "
                "limit, five seconds by default. The web converter is intended for "
                "short clips.",
            ),
        ),
        related=(
            "twitter-gif-to-mp4",
            "save-x-reaction-gifs",
            "save-x-gif-for-discord",
        ),
    ),
    LandingPage(
        slug="save-x-gif-for-discord",
        nav_label="Discord",
        h1_pre="Save an X GIF for ",
        h1_highlight="Discord",
        h1_post=" without blowing the upload limit",
        page_title="Save an X GIF for Discord - MP4 or Emoji-Ready GIF",
        description=(
            "Download an X (Twitter) GIF for Discord. Choose MP4 for chat, or "
            "convert to GIF for an emoji or sticker under Discord's size limits."
        ),
        eyebrow="Use case",
        lede=(
            "Discord handles video and GIFs differently depending on where you use "
            "them. A chat upload, an emoji, and a sticker each have their own rules. "
            "Pick the format that matches the slot."
        ),
        specs=(
            ("Best for chat", "MP4"),
            ("Best for emoji", "GIF, 256 KB or less"),
            ("Best for stickers", "PNG or GIF within Discord's limit"),
            ("Free upload", "10 MB per file at the time of writing"),
            ("Audio", "GIF posts are silent"),
            ("Conversion", "Optional, on the download page"),
        ),
        steps=(
            Step(
                "Copy the X post link",
                "Open the post with the GIF and choose Share, then Copy link.",
            ),
            Step(
                "Download the MP4",
                "Paste the link above and use the primary download button. This is "
                "the smallest, sharpest copy.",
            ),
            Step(
                "Upload, or convert for emoji",
                "Drag the MP4 into a Discord chat. For an emoji or sticker, convert "
                "to GIF and check the size first.",
            ),
        ),
        sections=(
            (
                "Chat: use the MP4",
                (
                    "Discord plays MP4 files inline and loops short silent clips. The "
                    "original MP4 from X is smaller and sharper than a converted GIF, "
                    "and it usually fits inside the free upload limit.",
                    "If Discord shows the file as a downloadable attachment instead of "
                    "a player, the clip may be too large or the client may not support "
                    "the codec. Try the desktop app or shorten the clip.",
                ),
            ),
            (
                "Emoji: convert to GIF first",
                (
                    "Custom emoji have a much smaller size cap than normal uploads. A "
                    "short, low-resolution GIF is the safest bet. Use the Convert "
                    "button, then check the file size before uploading.",
                    "Animated emoji need Nitro or a server with the right perks. "
                    "Without them, Discord may accept the file but only show the first "
                    "frame.",
                ),
            ),
            (
                "Stickers and reactions",
                (
                    "Stickers are static by default on many servers, so a PNG frame is "
                    "often enough. For animated stickers, keep the loop short and the "
                    "dimensions small.",
                    "You can also save a reaction GIF from a reply thread and use it as "
                    "a custom emoji, as long as the file stays under the limit and you "
                    "have permission to reuse it.",
                ),
            ),
            (
                "Size troubleshooting",
                (
                    "If Discord rejects the file, trim the clip or lower the source "
                    "resolution before converting again. The converter caps output "
                    "width and frame rate, but a long clip can still exceed a tight "
                    "emoji limit.",
                    "The MP4 download is always the smaller option for chat. Use GIF "
                    "only when a slot explicitly requires an image file.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Does Discord support GIFs?",
                "Yes, but Discord also plays MP4 files inline. For chat, the original "
                "MP4 is usually the better choice.",
            ),
            Faq(
                "How big can a Discord emoji be?",
                "Discord's emoji size limit is 256 KB. Stickers and normal uploads have "
                "different limits, so check the current value in Discord before "
                "uploading.",
            ),
            Faq(
                "Why does my GIF not animate in Discord?",
                "The file may be too large, the server may not support animated emoji, "
                "or Discord may have compressed it. Try a shorter, smaller GIF.",
            ),
            Faq(
                "Can I use the MP4 as a Discord emoji?",
                "No. Emoji slots accept image files. Convert to GIF and keep it under "
                "the emoji size limit.",
            ),
            Faq(
                "Will the download have audio?",
                "X GIFs are silent. If the source was a regular video, the MP4 may "
                "include audio.",
            ),
        ),
        related=(
            "twitter-gif-to-mp4",
            "save-x-gif-for-whatsapp",
            "download-x-gifs-on-pc",
        ),
    ),
    LandingPage(
        slug="save-x-gif-for-whatsapp",
        nav_label="WhatsApp",
        h1_pre="Save an X GIF for ",
        h1_highlight="WhatsApp",
        h1_post=" as a looping clip",
        page_title="Save an X GIF for WhatsApp - Loop It or Send as a Document",
        description=(
            "Download an X (Twitter) GIF for WhatsApp. Send the MP4 as a looping "
            "GIF, or convert to .gif and share it as a document."
        ),
        eyebrow="Use case",
        lede=(
            "WhatsApp calls short, silent videos GIFs, even though it sends them as "
            "MP4. That is convenient: the original X file usually works without any "
            "conversion."
        ),
        specs=(
            ("WhatsApp GIF format", "Short silent MP4"),
            ("Media size limit", "16 MB per chat upload at the time of writing"),
            ("Document limit", "Much larger; intended for files, not previews"),
            ("Best quality", "Original MP4"),
            ("True .gif", "Optional; send as document"),
            ("Audio", "None for X GIF posts"),
        ),
        steps=(
            Step(
                "Copy the X post link",
                "Use Share, then Copy link in the X app.",
            ),
            Step(
                "Download the MP4",
                "Paste the link above and use the MP4 button. This is the file "
                "WhatsApp will treat as a GIF.",
            ),
            Step(
                "Attach it in WhatsApp",
                "Pick the file from Downloads. For a real .gif, convert first and send "
                "it as a document.",
            ),
        ),
        sections=(
            (
                "Why WhatsApp loves MP4",
                (
                    "WhatsApp plays short silent MP4 loops automatically and labels "
                    "them as GIFs. Sending the original X MP4 keeps the quality and "
                    "usually stays inside the 16 MB chat media limit.",
                    "If you send a real .gif file, WhatsApp may treat it as a document "
                    "instead of an inline animation. The recipient then has to open it "
                    "manually.",
                ),
            ),
            (
                "When to convert to .gif",
                (
                    "Convert when you need a file that another app or archive "
                    "requires. For WhatsApp itself, conversion adds size without "
                    "improving playback.",
                    "If you do convert, send the GIF as a document so WhatsApp does not "
                    "try to compress it as media. The trade-off is that it will not "
                    "auto-loop in the chat.",
                ),
            ),
            (
                "Saving to your phone",
                (
                    "On Android, the downloaded MP4 lands in your Downloads folder and "
                    "can be shared straight from there. On iPhone, use Files, then "
                    "share the file into WhatsApp.",
                    "To keep a copy in Photos or Gallery, save the MP4 first. A "
                    "converted GIF may not appear as an animation in every gallery app.",
                ),
            ),
            (
                "Size and quality tips",
                (
                    "If WhatsApp refuses the file, trim the clip or try a shorter clip "
                    "from the same post. Very long videos are unlikely to fit under the "
                    "chat media limit.",
                    "Keep the original MP4 if you care about quality. Re-encoding to "
                    "GIF is only worth it for compatibility.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Are WhatsApp GIFs actually MP4?",
                "Yes. WhatsApp sends short silent videos and displays them as GIFs. The "
                "underlying file is usually MP4.",
            ),
            Faq(
                "Can I send a real GIF on WhatsApp?",
                "You can send one as a document, but it may not animate automatically "
                "in the chat.",
            ),
            Faq(
                "What is the WhatsApp media size limit?",
                "Chat media is capped at 16 MB at the time of writing. Documents can be "
                "much larger, but they do not preview like media.",
            ),
            Faq(
                "Why did my GIF lose quality?",
                "Re-encoding to GIF reduces color and may resize the clip. The MP4 "
                "download avoids that.",
            ),
            Faq(
                "Does this work on WhatsApp Web?",
                "Yes. Download the file on the same computer, then attach it in "
                "WhatsApp Web.",
            ),
        ),
        related=(
            "twitter-gif-to-mp4",
            "save-x-gif-for-discord",
            "download-x-gifs-on-android",
        ),
    ),
    LandingPage(
        slug="download-x-gifs-on-iphone",
        nav_label="iPhone",
        h1_pre="Download X GIFs on ",
        h1_highlight="iPhone",
        h1_post=" with Safari or any browser",
        page_title="How to Download X GIFs on iPhone - Step-by-Step",
        description=(
            "A step-by-step guide to saving X (Twitter) GIFs on iPhone. Copy the post "
            "link, download the MP4, and move it to Photos or Files."
        ),
        eyebrow="Platform guide",
        lede=(
            "You do not need an app or a shortcut for this. iOS can save an X GIF as "
            "an MP4 in a few taps, then you decide whether to keep it in Files or copy "
            "it into Photos."
        ),
        specs=(
            ("Browser", "Safari, Chrome, or any iOS browser"),
            ("Download format", "MP4 by default"),
            ("Saved location", "Files > Downloads"),
            ("Photos import", "Supported from Files"),
            ("GIF option", "Convert on the download page"),
            ("iOS version", "iOS 15 or newer recommended"),
        ),
        steps=(
            Step(
                "Copy the post link",
                "In the X app, tap the share icon on the post and choose Copy link. "
                "The post must be public.",
            ),
            Step(
                "Open the downloader in a browser",
                "Paste the link into the box at the top of this page and tap Get GIF.",
            ),
            Step(
                "Download the MP4",
                "On the download page, tap Download MP4. iOS saves it to Files > "
                "Downloads.",
            ),
            Step(
                "Move it where you want",
                "Open Files, long-press the file, and choose Share > Save to Photos, or "
                "share it directly into another app.",
            ),
        ),
        sections=(
            (
                "Where the file actually goes",
                (
                    "Safari does not put downloads in Photos. They go to the Downloads "
                    "folder in iCloud Drive or On My iPhone, depending on your "
                    "settings.",
                    "If you cannot find the file, open Files, tap Browse, then "
                    "Downloads. The most recent download is usually at the top.",
                ),
            ),
            (
                "GIFs and the Photos app",
                (
                    "Photos treats a .gif as an image, but whether it animates depends "
                    "on the app you view it in. Files previews it correctly; Photos may "
                    "show a still frame in some versions.",
                    "If animation matters, keep the file in Files or send it to an app "
                    "that supports animated GIFs. For most social sharing, the MP4 is "
                    "easier.",
                ),
            ),
            (
                "A note about Shortcuts and apps",
                (
                    "Shortcut-based downloaders often break when X changes its page "
                    "markup. The paste-and-download method here reads the public media "
                    "endpoint, so there is no shortcut to install or update.",
                    "You can still use a Shortcut to move the downloaded file into a "
                    "specific album after the fact.",
                ),
            ),
            (
                "Saving a reaction GIF from a reply",
                (
                    "Open the reply that contains the GIF, not the parent post. Copy "
                    "the reply's link, paste it here, and download. The tool resolves "
                    "the media attached to that specific post.",
                    "Only public replies work. A GIF inside a protected account's post "
                    "cannot be fetched.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Can I download an X GIF directly to Photos on iPhone?",
                "Not in one tap. iOS saves the MP4 to Files. Use Share > Save to Photos "
                "from the Files app.",
            ),
            Faq(
                "Why does my GIF show as an MP4?",
                "X stores GIFs as MP4. The default download preserves that original "
                "file. Use the Convert button for a .gif.",
            ),
            Faq(
                "Do I need an app?",
                "No. The downloader works in Safari or any iOS browser.",
            ),
            Faq(
                "Will it work on iPad?",
                "Yes. The same flow works on iPadOS.",
            ),
            Faq(
                "Why does the download fail?",
                "The post may be private, deleted, region-restricted, or temporarily "
                "rate-limited by X. Wait a minute and retry.",
            ),
        ),
        related=(
            "download-x-gifs-on-android",
            "download-x-gifs-on-pc",
            "twitter-gif-to-mp4",
        ),
    ),
    LandingPage(
        slug="download-x-gifs-on-android",
        nav_label="Android",
        h1_pre="Download X GIFs on ",
        h1_highlight="Android",
        h1_post=" in Chrome",
        page_title="How to Download X GIFs on Android - Chrome Guide",
        description=(
            "Save X (Twitter) GIFs on Android. Copy the post link, paste it in Chrome, "
            "download the MP4, and share it from Downloads."
        ),
        eyebrow="Platform guide",
        lede=(
            "Android handles the download cleanly: Chrome saves the MP4 to Downloads, "
            "and the share sheet can send it to WhatsApp, Telegram, Discord, or an "
            "editor."
        ),
        specs=(
            ("Browser", "Chrome, Firefox, Edge, or Samsung Internet"),
            ("Download format", "MP4 by default"),
            ("Saved location", "Downloads folder"),
            ("Gallery import", "Depends on the gallery app"),
            ("GIF option", "Convert on the download page"),
            ("Android version", "Android 8 or newer recommended"),
        ),
        steps=(
            Step(
                "Copy the post link",
                "In the X app, tap share on the post and choose Copy link.",
            ),
            Step(
                "Paste it into the downloader",
                "Use the box at the top of this page and tap Get GIF.",
            ),
            Step(
                "Tap Download MP4",
                "Chrome shows a download notification. The file is saved to Downloads.",
            ),
            Step(
                "Share or move it",
                "Open Downloads from the notification or your file manager, then share "
                "the file into another app.",
            ),
        ),
        sections=(
            (
                "Finding the file",
                (
                    "Chrome's Downloads page is the fastest route. Open the three-dot "
                    "menu, choose Downloads, and tap the most recent file. File managers "
                    "show it under Internal storage > Download.",
                    "Samsung Internet and Firefox use their own download folders, but "
                    "the share flow is the same.",
                ),
            ),
            (
                "Adding the MP4 to your gallery",
                (
                    "Not every gallery app imports MP4 files automatically. Google "
                    "Photos does not back up a file until it is in a scanned folder; a "
                    "file manager such as Files by Google can copy it into Movies.",
                    "For GIFs, the gallery may show a still preview. Use a GIF-aware app "
                    "if you need the animation.",
                ),
            ),
            (
                "Sharing to other apps",
                (
                    "The Android share sheet works directly from the download "
                    "notification. Tap Share and pick WhatsApp, Telegram, Discord, or "
                    "your editor.",
                    "If the target app rejects the file, check its size limit. "
                    "Converting to GIF usually makes the file larger, not smaller.",
                ),
            ),
            (
                "Reaction GIFs in replies",
                (
                    "Copy the link of the reply that contains the GIF, not the main "
                    "post. The resolver selects the media attached to that post.",
                    "A reply can contain several attachments. The resolver picks the "
                    "animated GIF or video; photo-only replies are rejected.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Where do downloaded X GIFs go on Android?",
                "Chrome saves them to the Downloads folder. Open the download "
                "notification or use a file manager to find them.",
            ),
            Faq(
                "Why is it an MP4, not a GIF?",
                "X stores GIFs as silent MP4 files. The default download keeps the "
                "original. Convert on the download page if you need a .gif.",
            ),
            Faq(
                "Can I make it my keyboard GIF?",
                "Some keyboards only accept GIFs. Convert the clip, keep it short, and "
                "check your keyboard app's size limit.",
            ),
            Faq(
                "Does it work on Samsung Internet?",
                "Yes. The paste-and-download flow is browser-independent.",
            ),
            Faq(
                "Why does the preview not play?",
                "The media URL may be region-restricted or expired. Try the MP4 "
                "download, which can still work even if the inline preview fails.",
            ),
        ),
        related=(
            "download-x-gifs-on-iphone",
            "save-x-gif-for-whatsapp",
            "twitter-gif-to-mp4",
        ),
    ),
    LandingPage(
        slug="download-x-gifs-on-pc",
        nav_label="Desktop",
        h1_pre="Download X GIFs on ",
        h1_highlight="PC or Mac",
        h1_post=" from your browser",
        page_title="How to Download X GIFs on PC and Mac",
        description=(
            "Download X (Twitter) GIFs on Windows or macOS. Paste the post link, save "
            "the original MP4, or convert it to a GIF."
        ),
        eyebrow="Platform guide",
        lede=(
            "On a computer you can skip the mobile share sheet entirely. Paste the "
            "post URL, download the file, and it lands in your browser's default "
            "download folder."
        ),
        specs=(
            ("Browsers", "Chrome, Edge, Firefox, Safari"),
            ("Download format", "Original MP4"),
            ("Windows default", "Downloads folder"),
            ("macOS default", "Downloads folder"),
            ("GIF option", "Convert on the download page"),
            ("Best for editing", "MP4"),
        ),
        steps=(
            Step(
                "Copy the post URL",
                "Open the post on x.com and copy the address, or use Share > Copy "
                "link.",
            ),
            Step(
                "Paste it above",
                "The resolver extracts the post ID and looks up the attached media.",
            ),
            Step(
                "Download MP4",
                "Use the primary button on the download page. The file streams directly "
                "from X's CDN.",
            ),
            Step(
                "Convert if needed",
                "Use the secondary button for a .gif only when a destination requires "
                "one.",
            ),
        ),
        sections=(
            (
                "Windows",
                (
                    "Chrome and Edge save to C:\\Users\\<you>\\Downloads by default. "
                    "Firefox may ask where to save on the first download. The file is "
                    "an MP4 even when the post is labelled GIF.",
                    "To import into an editor, drag the file from File Explorer into the "
                    "timeline. H.264 MP4 is widely supported.",
                ),
            ),
            (
                "macOS",
                (
                    "Safari and Chrome save to ~/Downloads. Open Finder and use "
                    "Command-Shift-L or the Downloads stack in the Dock.",
                    "QuickTime Player opens the MP4 directly. Preview may not loop it "
                    "the way X does, but the file is unchanged.",
                ),
            ),
            (
                "Working with the MP4",
                (
                    "MP4 is the better master copy for editing, archiving, and sharing. "
                    "It is smaller and has more color than a GIF.",
                    "If a forum, email client, or older tool rejects video, convert to "
                    "GIF. Expect a larger file and a reduced palette.",
                ),
            ),
            (
                "Batch downloads",
                (
                    "There is no bulk mode. The resolver handles one public post per "
                    "request, which keeps the service within rate limits and avoids "
                    "scraping.",
                    "For a handful of clips, open each post in a tab, copy the links, "
                    "and work through them one at a time.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "Can I right-click and save an X GIF?",
                "Right-clicking the player usually saves a poster image or a page link, "
                "not the media. Use the paste-and-download flow instead.",
            ),
            Faq(
                "Where is the downloaded file on Windows?",
                "Usually C:\\Users\\<you>\\Downloads, unless you changed Chrome or "
                "Edge's download settings.",
            ),
            Faq(
                "Where is it on macOS?",
                "In your user Downloads folder. Open it from Finder or the Dock's "
                "Downloads stack.",
            ),
            Faq(
                "Can I download a GIF from a protected post?",
                "No. Only public posts whose media is still on X's CDN can be fetched.",
            ),
            Faq(
                "Does the tool work without JavaScript?",
                "Yes. The form is a normal GET request to the resolver. JavaScript only "
                "adds the busy state on the button.",
            ),
        ),
        related=(
            "download-x-gifs-on-iphone",
            "download-x-gifs-on-android",
            "twitter-gif-to-mp4",
        ),
    ),
    LandingPage(
        slug="save-x-reaction-gifs",
        nav_label="Reaction GIFs",
        h1_pre="Save X ",
        h1_highlight="reaction GIFs",
        h1_post=" from replies at full quality",
        page_title="How to Save Reaction GIFs from X Replies",
        description=(
            "Download reaction GIFs from X (Twitter) replies without losing quality. "
            "Copy the reply link, paste it, and save the original MP4 or a converted "
            "GIF."
        ),
        eyebrow="How-to",
        lede=(
            "Reaction GIFs usually live in replies, not in the main post. The trick is "
            "to copy the link of the reply itself so the resolver fetches the right "
            "attachment."
        ),
        specs=(
            ("Where they live", "Reply posts and quote posts"),
            ("Link to copy", "The reply's /status/ URL"),
            ("Default download", "Phone-friendly MP4, no watermark"),
            ("Converted GIF", "Palette-based, width-capped"),
            ("Public posts only", "Yes"),
            ("Multiple attachments", "The animated one is selected"),
        ),
        steps=(
            Step(
                "Open the reply",
                "Find the reaction GIF in the thread and open that specific reply.",
            ),
            Step(
                "Copy the reply link",
                "Use Share > Copy link. Do not copy the parent post's URL.",
            ),
            Step(
                "Paste and download",
                "The download page previews the media attached to the reply. Save the "
                "MP4 or convert to GIF.",
            ),
        ),
        sections=(
            (
                "Why the reply link matters",
                (
                    "A parent post and its reply are different posts. If you paste the "
                    "parent URL, you get the parent's media, which may be a photo or "
                    "nothing at all.",
                    "The resolver reads the post ID in the URL, so the link must contain "
                    "/status/<id>. Profile links and search links are rejected.",
                ),
            ),
            (
                "Quality without re-encoding",
                (
                    "The MP4 button streams the file X uses in its player. That is the "
                    "highest-quality copy available publicly and the smallest file.",
                    "Converting to GIF re-encodes the clip. It is useful for "
                    "compatibility, but it is not lossless. Keep the MP4 if you want "
                    "the best master copy.",
                ),
            ),
            (
                "Reaction GIFs and credit",
                (
                    "Most reaction GIFs are short clips from films, TV, or someone "
                    "else's recording. Downloading does not make them yours to "
                    "republish commercially.",
                    "Credit the source when you can, and avoid using someone's face or "
                    "work in a way that implies endorsement.",
                ),
            ),
            (
                "When a GIF will not resolve",
                (
                    "Some replies contain a static image, a poll, or media that has "
                    "been deleted. The resolver rejects posts without animated_gif or "
                    "video attachments.",
                    "If X rate-limits the public endpoint, wait a minute. The tool does "
                    "not retry aggressively, which keeps it from being blocked.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "How do I download a GIF from a reply on X?",
                "Copy the reply's own link, not the parent post's link, then paste it "
                "into the downloader.",
            ),
            Faq(
                "Why did I get the wrong GIF?",
                "You probably pasted the parent post or a quote link. Use the URL of the "
                "specific reply that contains the GIF.",
            ),
            Faq(
                "Can I save a GIF from a quote post?",
                "Quoted media is not always attached to the quote post itself. If the "
                "resolver finds no animated media, open the original post and use its "
                "link.",
            ),
            Faq(
                "Is the download watermarked?",
                "No. The tool does not add a watermark. Any watermark already in the "
                "clip stays.",
            ),
            Faq(
                "Can I use reaction GIFs commercially?",
                "Only if you have the rights. Most reaction clips belong to their "
                "original creators or studios.",
            ),
        ),
        related=(
            "save-x-gif-for-discord",
            "save-x-gif-for-whatsapp",
            "why-twitter-converts-gifs-to-mp4",
        ),
    ),
)

PAGE_BY_SLUG: dict[str, LandingPage] = {page.slug: page for page in LANDING_PAGES}


def related_pages(page: LandingPage) -> tuple[LandingPage, ...]:
    return tuple(PAGE_BY_SLUG[slug] for slug in page.related if slug in PAGE_BY_SLUG)
