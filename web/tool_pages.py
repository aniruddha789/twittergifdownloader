from __future__ import annotations

from dataclasses import dataclass
from landing_pages import Faq, Step


@dataclass(frozen=True)
class ToolPreset:
    id: str
    label: str
    target_kb: int
    width: int
    height: int
    crop_mode: str  # "square" | "original"
    default_fps: int
    max_frames: int
    platform_name: str
    preview_style: str  # "discord-emoji" | "discord-sticker" | "slack-emoji" | "discord-chat"


@dataclass(frozen=True)
class ToolPage:
    slug: str
    nav_label: str
    short_action: str
    h1_pre: str
    h1_highlight: str
    h1_post: str
    page_title: str
    description: str
    eyebrow: str
    lede: str
    preset: ToolPreset
    budget_options_kb: tuple[tuple[int, str], ...]
    specs: tuple[tuple[str, str], ...]
    steps: tuple[Step, ...]
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    faqs: tuple[Faq, ...]
    related_tools: tuple[str, ...]
    related_guides: tuple[str, ...]
    updated: str = "2026-11-23"

    @property
    def title(self) -> str:
        return f"{self.h1_pre}{self.h1_highlight}{self.h1_post}".strip()

    @property
    def path(self) -> str:
        return f"/{self.slug}"


TOOL_PAGES: tuple[ToolPage, ...] = (
    ToolPage(
        slug="discord-emoji-maker",
        nav_label="Discord Emoji Maker",
        short_action="Make Discord Emoji (<256KB)",
        h1_pre="Discord ",
        h1_highlight="Emoji Maker",
        h1_post=" — 128×128 Animated GIFs Under 256 KB",
        page_title="Discord Emoji Maker - Resize & Compress GIFs Under 256KB (128x128)",
        description=(
            "Free browser-based Discord animated emoji maker. Crop any GIF or X/Twitter "
            "MP4 clip to a 128x128 square and auto-compress it under Discord's strict "
            "256 KB limit with live dark/light chat preview."
        ),
        eyebrow="100% Browser Tool · No Upload",
        lede=(
            "Drop any GIF, MP4, or WebM clip—or send one straight from the X downloader. "
            "Frame a 1:1 square crop, preview how it reads at 22px inline and 48px "
            "reaction size, and auto-fit Discord's strict 256 KB animated emoji cap right in your tab."
        ),
        preset=ToolPreset(
            id="discord_emoji",
            label="Discord Emoji (128×128 · <256 KB)",
            target_kb=256,
            width=128,
            height=128,
            crop_mode="square",
            default_fps=15,
            max_frames=60,
            platform_name="Discord",
            preview_style="discord-emoji",
        ),
        budget_options_kb=(
            (256, "256 KB (Discord Emoji Limit)"),
            (128, "128 KB (Ultra-Light / Slack)"),
            (512, "512 KB (Sticker Budget)"),
        ),
        specs=(
            ("Output dimensions", "128 × 128 px (1:1 square)"),
            ("Max file size", "Strictly under 256 KB (262,144 bytes)"),
            ("Chat display size", "22 × 22 px inline · 48 × 48 px jumbo"),
            ("Accepted inputs", "GIF, MP4, WebM, or X post handoff"),
            ("Auto-compression", "Palette + FPS + dimension ladder"),
            ("Privacy", "100% client-side in your browser"),
        ),
        steps=(
            Step(
                "Load a GIF, MP4, or X clip",
                "Drop a local .gif, .mp4, or .webm file into the studio—or click "
                "'Make Discord Emoji' directly from any X (Twitter) download page.",
            ),
            Step(
                "Frame the 1:1 square crop",
                "Drag the preview canvas to pan and use the zoom slider to cut out "
                "empty margins so your subject stays readable at 22 pixels in chat.",
            ),
            Step(
                "Auto-fit under 256 KB & download",
                "The encoder automatically tunes color palette depth and frame cadence "
                "until the badge turns green under 256 KB. Check the Dark and Light "
                "chat preview, then save your .gif.",
            ),
        ),
        sections=(
            (
                "Why Discord rejects most animated GIFs as emojis",
                (
                    "Discord's server emoji uploader enforces a hard 256 KB ceiling "
                    "and scales every upload down to 128 × 128 pixels. A typical two-second "
                    "reaction clip saved from X or converted with default settings weighs "
                    "between 1.2 MB and 4 MB—more than ten times what Discord allows.",
                    "Even when you resize a clip to 128 × 128 manually, a full 256-color "
                    "table at 20+ frames per second often lands around 350–600 KB. This "
                    "tool runs an iterative client-side compression loop that steps color "
                    "palettes (256 down to 32 colors) before thinning frames, so motion "
                    "stays smooth while the final byte count lands safely under 256 KB.",
                ),
            ),
            (
                "Designing for 22-pixel and 48-pixel chat readability",
                (
                    "Although you upload a 128 × 128 file, Discord renders custom emojis "
                    "at just 22 × 22 pixels when typed inside a text message and 48 × 48 "
                    "pixels when posted by themselves as 'jumbo' emojis. Wide landscape "
                    "video clips shrink the face or action into an unrecognizable speck.",
                    "Use the interactive 1:1 crop box and zoom slider to crop tightly around "
                    "the face, character, or gesture. Toggle between 'Cover (1:1 Crop)' and "
                    "'Fit Inside Square' and inspect the simulated Discord dark-mode (#313338) "
                    "and light-mode (#ffffff) chat bubbles before exporting.",
                ),
            ),
            (
                "How to upload your animated emoji to a Discord server",
                (
                    "Open your Discord server on desktop or mobile, go to Server Settings → "
                    "Emoji, and click Upload Emoji. Select the 128 × 128 .gif file you "
                    "downloaded here and give it a short shortcode alias (letters, numbers, "
                    "and underscores, at least 2 characters).",
                    "Note that uploading an animated GIF consumes one of your server's "
                    "animated emoji slots, and using animated server emojis across chats "
                    "requires an active Discord Nitro or Nitro Basic subscription.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "What are Discord's exact animated emoji size and dimension limits?",
                "Discord requires animated server emojis to be GIF files under 256 KB "
                "(262,144 bytes) and recommends a 128 × 128 pixel square aspect ratio.",
            ),
            Faq(
                "How does the auto-compression loop keep GIFs under 256 KB?",
                "It encodes at 128 × 128 first, then steps down color palette size "
                "(256 → 128 → 64 → 32 colors) and frame rate (15 → 12 → 10 → 8 fps) "
                "until the output strictly passes the 256 KB budget.",
            ),
            Faq(
                "Can I turn an X (Twitter) MP4 clip directly into a Discord emoji?",
                "Yes. Either drop any downloaded .mp4 file into the studio or click "
                "'Make Discord Emoji (<256KB)' on our X download page to load the clip "
                "directly into the editor without re-uploading.",
            ),
            Faq(
                "Are my GIFs or videos uploaded to a server?",
                "No. Frame extraction, square cropping, palette quantization, and GIF "
                "encoding all run 100% locally inside your browser using HTML5 Canvas "
                "and a Web Worker.",
            ),
            Faq(
                "What if my video clip is 10 seconds long and still over 256 KB?",
                "Use the Trim Start and Trim End sliders in the studio to isolate the "
                "best 1.5 to 3 seconds of action. Shorter loops allow higher frame rates "
                "and richer color palettes within 256 KB.",
            ),
        ),
        related_tools=(
            "discord-sticker-maker",
            "slack-emoji-maker",
            "discord-gif-compressor",
        ),
        related_guides=(
            "save-x-gif-for-discord",
            "twitter-gif-to-mp4",
            "save-x-reaction-gifs",
        ),
    ),
    ToolPage(
        slug="discord-sticker-maker",
        nav_label="Discord Sticker Maker",
        short_action="Make Discord Sticker (<512KB)",
        h1_pre="Discord ",
        h1_highlight="Sticker Maker",
        h1_post=" — 320×320 Animated Stickers Under 512 KB",
        page_title="Discord Sticker Maker - 320x320 Animated GIF Converter (<512KB)",
        description=(
            "Create custom 320x320 animated Discord stickers under the 512 KB limit "
            "in your browser. Crop MP4s or GIFs to 1:1, preview on dark and light "
            "themes, and compress automatically."
        ),
        eyebrow="100% Browser Tool · No Upload",
        lede=(
            "Turn any X (Twitter) clip, MP4, or GIF into a crisp 320×320 animated "
            "sticker. Frame your 1:1 square crop, preview it at Discord's 160px chat "
            "sticker size, and auto-compress under the 512 KB upload ceiling."
        ),
        preset=ToolPreset(
            id="discord_sticker",
            label="Discord Sticker (320×320 · <512 KB)",
            target_kb=512,
            width=320,
            height=320,
            crop_mode="square",
            default_fps=12,
            max_frames=60,
            platform_name="Discord",
            preview_style="discord-sticker",
        ),
        budget_options_kb=(
            (512, "512 KB (Discord Sticker Limit)"),
            (256, "256 KB (Emoji Budget)"),
            (1024, "1 MB (High-Detail Archive)"),
        ),
        specs=(
            ("Output dimensions", "320 × 320 px (exact Discord spec)"),
            ("Max file size", "Strictly under 512 KB (524,288 bytes)"),
            ("Chat display size", "160 × 160 px in message feed"),
            ("Recommended duration", "1.5 to 4.0 seconds"),
            ("Accepted inputs", "GIF, MP4, WebM, or X post handoff"),
            ("Privacy", "100% client-side browser processing"),
        ),
        steps=(
            Step(
                "Drop a video or GIF clip",
                "Select a local .mp4, .webm, or .gif file, or send a clip straight "
                "from the X GIF downloader with one click.",
            ),
            Step(
                "Crop to 320×320 & trim the loop",
                "Pan and zoom the 1:1 crop box so the reaction fills the 320×320 "
                "square, and trim dead frames at the start or end.",
            ),
            Step(
                "Auto-compress under 512 KB",
                "Let the smart compressor balance palette colors, frame rate, and "
                "resolution until the file badge reads green under 512 KB.",
            ),
        ),
        sections=(
            (
                "Understanding Discord's 320×320 and 512 KB sticker rules",
                (
                    "Discord custom stickers display much larger in chat than emojis "
                    "(160 × 160 pixels in the message timeline and 320 × 320 pixels at "
                    "native resolution), yet Discord only gives you double the file size "
                    "budget: 512 KB maximum.",
                    "Because a 320 × 320 canvas has 6.25 times as many pixels per frame "
                    "as a 128 × 128 emoji, raw unoptimized GIFs at 320 × 320 almost always "
                    "exceed 1.5 MB. Our auto-compression engine prioritizes clean spatial "
                    "detail while tuning color tables (192 to 48 colors) and frame pacing "
                    "(10–15 fps) so your sticker uploads on the first try.",
                ),
            ),
            (
                "GIF vs. APNG for Discord stickers",
                (
                    "Discord's server sticker uploader accepts PNG, APNG, and GIF files "
                    "under 512 KB (for servers with sticker slots unlocked via Server "
                    "Boosts). When starting from an X/Twitter reaction clip or MP4 video, "
                    "a palette-quantized GIF with controlled color depth is far easier "
                    "to fit under 512 KB than a 24-bit APNG.",
                    "To get the sharpest 320 × 320 sticker, keep your clip between 1.5 "
                    "and 3.5 seconds using the Trim Start and Trim End controls. Fewer "
                    "total frames allow the optimizer to keep the full 320 × 320 resolution "
                    "and a richer color palette without downscaling.",
                ),
            ),
            (
                "Uploading custom stickers to your Discord server",
                (
                    "On desktop Discord, open Server Settings → Stickers and click "
                    "Upload Sticker. Choose your downloaded .gif file, pick a related "
                    "Unicode emoji tag (so members receive sticker suggestions as they "
                    "type), and add a short name and description.",
                    "Always test how the sticker looks against both dark and light "
                    "backgrounds using our live chat preview box—dark scenes with black "
                    "borders can blend into Discord's dark theme unless framed tightly.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "What size and file limit does Discord require for stickers?",
                "Discord requires custom stickers to be 320 × 320 pixels and strictly "
                "under 512 KB (524,288 bytes), with a duration under 5 seconds.",
            ),
            Faq(
                "Why did the optimizer step my sticker down from 320×320 to 256×256?",
                "If a clip has high-motion noise across 40+ frames, even a 32-color "
                "palette at 320 × 320 can exceed 512 KB. Trimming the clip to 2–3 "
                "seconds lets the encoder preserve full 320 × 320 resolution.",
            ),
            Faq(
                "Can I use this with an MP4 downloaded from X (Twitter)?",
                "Yes. Drop any MP4 directly into the tool or click 'Make Discord Sticker' "
                "on our X download page to load and crop the video in your browser.",
            ),
            Faq(
                "Do I need Server Boosts to upload animated stickers on Discord?",
                "Discord unlocks 5 free custom sticker slots at Base level and adds more "
                "slots at Boost Levels 1, 2, and 3. You also need the 'Manage Expressions' "
                "permission on the server.",
            ),
        ),
        related_tools=(
            "discord-emoji-maker",
            "discord-gif-compressor",
            "slack-emoji-maker",
        ),
        related_guides=(
            "save-x-gif-for-discord",
            "save-x-reaction-gifs",
            "twitter-gif-to-mp4",
        ),
    ),
    ToolPage(
        slug="slack-emoji-maker",
        nav_label="Slack Emoji Maker",
        short_action="Make Slack Emoji (<128KB)",
        h1_pre="Slack ",
        h1_highlight="Emoji Maker",
        h1_post=" — 128×128 Animated GIFs Under 128 KB",
        page_title="Slack Emoji Maker - Resize & Compress Animated GIFs Under 128KB",
        description=(
            "Make custom animated Slack emojis that pass Slack's strict 128 KB and "
            "50-frame limits. Crop any GIF or MP4 to 128x128 in your browser with "
            "zero server upload."
        ),
        eyebrow="100% Browser Tool · No Upload",
        lede=(
            "Slack has the strictest custom emoji rules of any team chat app: 128×128 "
            "square, under 128 KB, and no more than 50 frames. Drop any GIF or MP4 "
            "and let the studio crop, thin frames, and compress it automatically."
        ),
        preset=ToolPreset(
            id="slack_emoji",
            label="Slack Emoji (128×128 · <128 KB · ≤50 frames)",
            target_kb=128,
            width=128,
            height=128,
            crop_mode="square",
            default_fps=12,
            max_frames=50,
            platform_name="Slack",
            preview_style="slack-emoji",
        ),
        budget_options_kb=(
            (128, "128 KB (Slack Emoji Limit)"),
            (64, "64 KB (Ultra-Compact)"),
            (256, "256 KB (Discord Emoji Limit)"),
        ),
        specs=(
            ("Output dimensions", "128 × 128 px (1:1 square)"),
            ("Max file size", "Strictly under 128 KB (131,072 bytes)"),
            ("Max frame count", "Capped at 50 frames (Slack hard rule)"),
            ("Chat display size", "22 × 22 px inline · 32 × 32 px reaction"),
            ("Accepted inputs", "GIF, MP4, WebM, or X post handoff"),
            ("Privacy", "100% local in-browser processing"),
        ),
        steps=(
            Step(
                "Drop a GIF or video clip",
                "Open any .gif, .mp4, or .webm from your device—or pass an X reaction "
                "GIF straight from our download page.",
            ),
            Step(
                "Crop tightly to a 1:1 square",
                "Pan and zoom the crop box around the subject. Tight framing prevents "
                "your Slack emoji from turning into an unreadable dot in channel threads.",
            ),
            Step(
                "Auto-compress under 128 KB & 50 frames",
                "The encoder enforces Slack's 50-frame cap and steps down palette "
                "colors and frame rate until the file fits under 128 KB.",
            ),
        ),
        sections=(
            (
                "Why Slack rejects GIFs that work on Discord",
                (
                    "A custom emoji that uploads fine to Discord will fail in Slack half "
                    "the time. Slack enforces two separate limits on animated emojis: the "
                    "file size must stay under 128 KB (half of Discord's 256 KB allowance) "
                    "and the animation cannot exceed 50 total frames.",
                    "Our Slack preset enforces both constraints simultaneously. Before "
                    "encoding even starts, the frame sampler caps the clip at 50 frames "
                    "(adjusting frame delay so playback speed stays natural), then runs "
                    "the palette and dimension search until the output is under 128 KB.",
                ),
            ),
            (
                "Tips for crisp animated Slack reactions",
                (
                    "Slack renders inline emojis at 22 × 22 pixels inside messages and "
                    "around 16–20 pixels inside reaction pills under a post. High-detail "
                    "video backgrounds waste kilobytes and blur the focal point.",
                    "Zoom in on the main subject using the 1:1 crop box, trim the clip "
                    "to a snappy 1.5–2.5 second loop, and check both the Slack Dark "
                    "(#1a1d21) and Slack Light (#ffffff) chat previews. Because everything "
                    "runs locally in your browser, internal company clips or team "
                    "recordings never leave your machine.",
                ),
            ),
            (
                "How to add your custom emoji to a Slack workspace",
                (
                    "In Slack on desktop, click the smiley face (Emoji) icon in any "
                    "message box, click Add Emoji at the bottom-left, and switch to the "
                    "Upload Image tab. Select your 128 × 128 .gif file and type a "
                    "memorable `:shortcode:` name.",
                    "If you do not see the Add Emoji button, your workspace owners may "
                    "have restricted custom emoji creation to admins and managers.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "What are Slack's exact custom animated emoji limits?",
                "Slack recommends 128 × 128 pixel square GIFs under 128 KB in file "
                "size and rejects animated GIFs with more than 50 frames.",
            ),
            Faq(
                "Does this tool automatically limit my GIF to 50 frames?",
                "Yes. The Slack preset caps extraction at 50 frames and recalculates "
                "per-frame delay in centiseconds so the loop plays at normal speed.",
            ),
            Faq(
                "Is it safe to use for internal team or company videos?",
                "Yes. All decoding, cropping, and GIF encoding happen locally inside "
                "your browser tab. No files are uploaded to our servers.",
            ),
            Faq(
                "How do I keep the image sharp under 128 KB?",
                "Trim the clip to 1.5–2 seconds so it only needs 18–24 frames. With "
                "fewer frames, the auto-compressor can keep full 128 × 128 resolution "
                "and 128+ colors while staying under 128 KB.",
            ),
        ),
        related_tools=(
            "discord-emoji-maker",
            "discord-sticker-maker",
            "discord-gif-compressor",
        ),
        related_guides=(
            "save-x-gif-for-discord",
            "download-x-gifs-on-pc",
            "why-twitter-converts-gifs-to-mp4",
        ),
    ),
    ToolPage(
        slug="discord-gif-compressor",
        nav_label="Discord GIF Compressor",
        short_action="Compress GIF for Discord",
        h1_pre="Discord ",
        h1_highlight="GIF Compressor",
        h1_post=" — Shrink GIFs & MP4s to 256 KB or 8 MB",
        page_title="Discord GIF Compressor - Shrink GIFs Under 256KB, 512KB, or 8MB",
        description=(
            "Compress oversized GIFs and X/Twitter MP4 clips in your browser to fit "
            "Discord's 256 KB emoji, 512 KB sticker, or 8 MB chat upload limits. "
            "Keep original aspect ratio or crop 1:1."
        ),
        eyebrow="100% Browser Tool · No Upload",
        lede=(
            "Stop getting 'Your files are too powerful' upload errors. Drop any GIF "
            "or MP4, pick an exact target byte ceiling (256 KB, 512 KB, 2 MB, or 8 MB), "
            "and let the browser compressor shrink it while preserving aspect ratio."
        ),
        preset=ToolPreset(
            id="discord_compressor",
            label="Discord GIF Compressor (Original Ratio · Target Size)",
            target_kb=256,
            width=480,
            height=0,
            crop_mode="original",
            default_fps=15,
            max_frames=90,
            platform_name="Discord",
            preview_style="discord-chat",
        ),
        budget_options_kb=(
            (256, "256 KB (Discord Emoji)"),
            (512, "512 KB (Discord Sticker)"),
            (2048, "2 MB (Fast Chat GIF)"),
            (8192, "8 MB (Discord Chat Safe)"),
        ),
        specs=(
            ("Aspect ratio", "Original ratio (or optional 1:1 square)"),
            ("Target size presets", "256 KB · 512 KB · 2 MB · 8 MB"),
            ("Max output width", "Configurable from 128 px up to 640 px"),
            ("Compression method", "Adaptive palette + frame rate + scale search"),
            ("Accepted inputs", "GIF, MP4, WebM, or X post handoff"),
            ("Privacy", "100% client-side in your browser"),
        ),
        steps=(
            Step(
                "Drop your oversized GIF or MP4",
                "Select a local .gif, .mp4, or .webm file—or click 'Compress GIF for "
                "Discord' from any X (Twitter) download page.",
            ),
            Step(
                "Pick your target file size ceiling",
                "Choose 256 KB for server emojis, 512 KB for stickers, 2 MB for snappy "
                "mobile chat embeds, or 8 MB for full-width clips.",
            ),
            Step(
                "Preview savings & download",
                "Compare the output size badge and before/after savings percentage, "
                "inspect the live chat embed preview, and save your compressed .gif.",
            ),
        ),
        sections=(
            (
                "How target-size GIF compression works in your browser",
                (
                    "Standard GIF encoders force you to guess a width, frame rate, and "
                    "color count, encode the file, see that it is still too large, and "
                    "start over. Because GIF uses 1980s LZW compression over a per-frame "
                    "color table, small changes in palette size or frame stride produce "
                    "dramatic file-size swings.",
                    "This compressor reverses the workflow: you pick the maximum file "
                    "size you can afford (256 KB, 512 KB, 2 MB, or 8 MB) and the Web "
                    "Worker searches a prioritized quality ladder. It tries full width "
                    "with a tighter color palette first, then trims redundant intermediate "
                    "frames, and only lowers dimensions when necessary to guarantee the "
                    "file fits.",
                ),
            ),
            (
                "Keeping original aspect ratio vs. 1:1 square cropping",
                (
                    "Unlike the dedicated emoji and sticker makers—which default to a "
                    "1:1 square—the Discord GIF Compressor preserves your clip's original "
                    "widescreen (16:9), vertical (9:16), or classic (4:3) aspect ratio "
                    "so reaction scenes and subtitles stay intact in chat messages.",
                    "If you decide mid-edit that you want a square reaction instead, "
                    "toggle the Framing mode to '1:1 Square Crop' at any time without "
                    "reloading your file.",
                ),
            ),
            (
                "When to use a compressed .GIF vs. an MP4 on Discord",
                (
                    "For regular Discord chat messages, posting X's original MP4 is "
                    "almost always smaller and sharper. However, you need a true compressed "
                    ".gif file whenever you want the clip to be starred into your "
                    "Discord GIF Favorites drawer, uploaded as a server emoji/sticker, "
                    "or embedded in GitHub READMEs, forums, and documentation.",
                ),
            ),
        ),
        faqs=(
            Faq(
                "How much can I shrink an animated GIF without ruining it?",
                "Most uncompressed or raw-converted GIFs shrink by 50% to 85% by dropping "
                "the color palette from 256 to 128 or 64 colors and capping frame rate "
                "at 12–15 fps.",
            ),
            Faq(
                "Why does a GIF need to be under 256 KB or 8 MB for Discord?",
                "Discord enforces a strict 256 KB cap on custom emojis, 512 KB on custom "
                "stickers, and 8–10 MB on free-tier message attachments depending on "
                "region and experiment rollout.",
            ),
            Faq(
                "Can I compress an MP4 video into a small GIF with this tool?",
                "Yes. You can load an .mp4 or .webm directly (or send one from our X "
                "downloader) and export an optimized .gif that hits your target byte budget.",
            ),
            Faq(
                "Are my files uploaded to any server during compression?",
                "No. Every compression pass runs inside your own browser using HTML5 "
                "Canvas and a local Web Worker.",
            ),
        ),
        related_tools=(
            "discord-emoji-maker",
            "discord-sticker-maker",
            "slack-emoji-maker",
        ),
        related_guides=(
            "save-x-gif-for-discord",
            "twitter-gif-to-mp4",
            "why-twitter-converts-gifs-to-mp4",
        ),
    ),
)

TOOL_BY_SLUG: dict[str, ToolPage] = {tool.slug: tool for tool in TOOL_PAGES}


def related_tool_pages(tool: ToolPage) -> tuple[ToolPage, ...]:
    return tuple(TOOL_BY_SLUG[slug] for slug in tool.related_tools if slug in TOOL_BY_SLUG)
