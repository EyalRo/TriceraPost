const std = @import("std");

const allocator = std.heap.wasm_allocator;
const Result = struct {
    size: u32,
    flags: u32,
};

const FLAG_NZB: u32 = 1;
const TagMask = u64;

const TAG_RES_2160P: u6 = 0;
const TAG_RES_1080P: u6 = 1;
const TAG_RES_720P: u6 = 2;
const TAG_RES_576P: u6 = 3;
const TAG_RES_480P: u6 = 4;
const TAG_HDR_HDR10P: u6 = 5;
const TAG_HDR_HDR10: u6 = 6;
const TAG_HDR_DV: u6 = 7;
const TAG_HDR_HLG: u6 = 8;
const TAG_HDR_SDR: u6 = 9;
const TAG_FMT_HEVC: u6 = 10;
const TAG_FMT_H264: u6 = 11;
const TAG_FMT_AV1: u6 = 12;
const TAG_FMT_VP9: u6 = 13;
const TAG_SRC_WEBDL: u6 = 14;
const TAG_SRC_WEBRIP: u6 = 15;
const TAG_SRC_BLURAY: u6 = 16;
const TAG_SRC_HDTV: u6 = 17;
const TAG_SRC_REMUX: u6 = 18;
const TAG_SRC_UHD: u6 = 19;
const TAG_AUD_DTS: u6 = 20;
const TAG_AUD_TRUEHD: u6 = 21;
const TAG_AUD_ATMOS: u6 = 22;
const TAG_AUD_AAC: u6 = 23;
const TAG_AUD_EAC3: u6 = 24;
const TAG_AUD_AC3: u6 = 25;
const TAG_CONT_MKV: u6 = 26;
const TAG_CONT_MP4: u6 = 27;
const TAG_CONT_AVI: u6 = 28;
const TAG_OTHER_REPACK: u6 = 29;
const TAG_OTHER_PROPER: u6 = 30;
const TAG_OTHER_REMASTERED: u6 = 31;
const TAG_OTHER_EXTENDED: u6 = 32;
const TAG_OTHER_10BIT: u6 = 33;

pub export fn alloc(size: usize) usize {
    const buf = allocator.alloc(u8, size) catch return 0;
    return @intFromPtr(buf.ptr);
}

pub export fn dealloc(ptr: usize, size: usize) void {
    if (ptr == 0 or size == 0) return;
    const slice = @as([*]u8, @ptrFromInt(ptr))[0..size];
    allocator.free(slice);
}

fn readU32(buf: []const u8, idx: *usize) !u32 {
    if (idx.* + 4 > buf.len) return error.OutOfBounds;
    const b0 = @as(u32, buf[idx.*]);
    const b1 = @as(u32, buf[idx.* + 1]);
    const b2 = @as(u32, buf[idx.* + 2]);
    const b3 = @as(u32, buf[idx.* + 3]);
    const value = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
    idx.* += 4;
    return value;
}

fn readBytes(buf: []const u8, idx: *usize, len: usize) ![]const u8 {
    if (idx.* + len > buf.len) return error.OutOfBounds;
    const slice = buf[idx.* .. idx.* + len];
    idx.* += len;
    return slice;
}

fn isWordChar(ch: u8) bool {
    return (ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') or (ch >= '0' and ch <= '9') or (ch == '_');
}

fn asciiLower(ch: u8) u8 {
    if (ch >= 'A' and ch <= 'Z') return ch + 32;
    return ch;
}

fn matchesAt(text: []const u8, token: []const u8, idx: usize) bool {
    if (idx + token.len > text.len) return false;
    var j: usize = 0;
    while (j < token.len) : (j += 1) {
        if (asciiLower(text[idx + j]) != asciiLower(token[j])) return false;
    }
    return true;
}

fn containsToken(text: []const u8, token: []const u8) bool {
    if (token.len == 0 or token.len > text.len) return false;
    var i: usize = 0;
    while (i + token.len <= text.len) : (i += 1) {
        if (!matchesAt(text, token, i)) continue;
        if (i > 0 and isWordChar(text[i - 1])) continue;
        const next_idx = i + token.len;
        if (next_idx < text.len and isWordChar(text[next_idx])) continue;
        return true;
    }
    return false;
}

fn containsAny(text: []const u8, tokens: []const []const u8) bool {
    for (tokens) |token| {
        if (containsToken(text, token)) return true;
    }
    return false;
}

fn tagMask(text: []const u8) TagMask {
    var mask: TagMask = 0;
    if (containsToken(text, "2160p")) mask |= @as(TagMask, 1) << TAG_RES_2160P;
    if (containsToken(text, "1080p")) mask |= @as(TagMask, 1) << TAG_RES_1080P;
    if (containsToken(text, "720p")) mask |= @as(TagMask, 1) << TAG_RES_720P;
    if (containsToken(text, "576p")) mask |= @as(TagMask, 1) << TAG_RES_576P;
    if (containsToken(text, "480p")) mask |= @as(TagMask, 1) << TAG_RES_480P;

    if (containsToken(text, "hdr10+") or containsToken(text, "hdr10plus")) {
        mask |= @as(TagMask, 1) << TAG_HDR_HDR10P;
    }
    if (containsToken(text, "hdr10")) mask |= @as(TagMask, 1) << TAG_HDR_HDR10;
    if (containsToken(text, "dolby vision") or containsToken(text, "dolby-vision") or containsToken(text, "dv")) {
        mask |= @as(TagMask, 1) << TAG_HDR_DV;
    }
    if (containsToken(text, "hlg")) mask |= @as(TagMask, 1) << TAG_HDR_HLG;
    if (containsToken(text, "sdr")) mask |= @as(TagMask, 1) << TAG_HDR_SDR;

    if (containsAny(text, &[_][]const u8{ "x265", "h265", "h.265", "hevc" })) {
        mask |= @as(TagMask, 1) << TAG_FMT_HEVC;
    }
    if (containsAny(text, &[_][]const u8{ "x264", "h264", "h.264", "avc" })) {
        mask |= @as(TagMask, 1) << TAG_FMT_H264;
    }
    if (containsToken(text, "av1")) mask |= @as(TagMask, 1) << TAG_FMT_AV1;
    if (containsToken(text, "vp9")) mask |= @as(TagMask, 1) << TAG_FMT_VP9;

    if (containsAny(text, &[_][]const u8{ "web-dl", "web.dl", "web dl", "webdl" })) {
        mask |= @as(TagMask, 1) << TAG_SRC_WEBDL;
    }
    if (containsToken(text, "webrip")) mask |= @as(TagMask, 1) << TAG_SRC_WEBRIP;
    if (containsAny(text, &[_][]const u8{ "bluray", "blu-ray", "blu ray" })) {
        mask |= @as(TagMask, 1) << TAG_SRC_BLURAY;
    }
    if (containsToken(text, "hdtv")) mask |= @as(TagMask, 1) << TAG_SRC_HDTV;
    if (containsToken(text, "remux")) mask |= @as(TagMask, 1) << TAG_SRC_REMUX;
    if (containsToken(text, "uhd")) mask |= @as(TagMask, 1) << TAG_SRC_UHD;

    if (containsAny(text, &[_][]const u8{ "dts-hd", "dts hd", "dtshd", "dts" })) {
        mask |= @as(TagMask, 1) << TAG_AUD_DTS;
    }
    if (containsToken(text, "truehd")) mask |= @as(TagMask, 1) << TAG_AUD_TRUEHD;
    if (containsToken(text, "atmos")) mask |= @as(TagMask, 1) << TAG_AUD_ATMOS;
    if (containsToken(text, "aac")) mask |= @as(TagMask, 1) << TAG_AUD_AAC;
    if (containsAny(text, &[_][]const u8{ "eac3", "ddp" })) {
        mask |= @as(TagMask, 1) << TAG_AUD_EAC3;
    }
    if (containsAny(text, &[_][]const u8{ "ac3", "dolby digital" })) {
        mask |= @as(TagMask, 1) << TAG_AUD_AC3;
    }

    if (containsToken(text, "mkv")) mask |= @as(TagMask, 1) << TAG_CONT_MKV;
    if (containsToken(text, "mp4")) mask |= @as(TagMask, 1) << TAG_CONT_MP4;
    if (containsToken(text, "avi")) mask |= @as(TagMask, 1) << TAG_CONT_AVI;

    if (containsToken(text, "repack")) mask |= @as(TagMask, 1) << TAG_OTHER_REPACK;
    if (containsToken(text, "proper")) mask |= @as(TagMask, 1) << TAG_OTHER_PROPER;
    if (containsToken(text, "remastered")) mask |= @as(TagMask, 1) << TAG_OTHER_REMASTERED;
    if (containsToken(text, "extended")) mask |= @as(TagMask, 1) << TAG_OTHER_EXTENDED;
    if (containsAny(text, &[_][]const u8{ "10bit", "10-bit", "10 bit" })) {
        mask |= @as(TagMask, 1) << TAG_OTHER_10BIT;
    }
    return mask;
}

fn hasNzb(subject: []const u8) bool {
    if (subject.len < 4) return false;
    var i: usize = 0;
    while (i + 3 < subject.len) : (i += 1) {
        if (subject[i] != '.') continue;
        if (asciiLower(subject[i + 1]) != 'n') continue;
        if (asciiLower(subject[i + 2]) != 'z') continue;
        if (asciiLower(subject[i + 3]) != 'b') continue;
        const next_idx = i + 4;
        if (next_idx >= subject.len) return true;
        if (!isWordChar(subject[next_idx])) return true;
    }
    return false;
}

fn parseSize(size_raw: []const u8) u32 {
    if (size_raw.len == 0) return 0;
    var value: u64 = 0;
    for (size_raw) |ch| {
        if (ch < '0' or ch > '9') return 0;
        value = value * 10 + @as(u64, ch - '0');
        if (value > std.math.maxInt(u32)) return std.math.maxInt(u32);
    }
    return @intCast(value);
}

pub export fn parse_overviews(in_ptr: usize, in_len: usize, out_ptr: usize, out_len: usize) u32 {
    if (in_ptr == 0 or out_ptr == 0) return 1;
    const input = @as([*]const u8, @ptrFromInt(in_ptr))[0..in_len];
    var idx: usize = 0;
    const count = readU32(input, &idx) catch return 1;
    const needed = @as(usize, count) * @sizeOf(Result);
    if (out_len < needed) return 2;

    var out_index: usize = 0;
    while (out_index < count) : (out_index += 1) {
        const subject_len = readU32(input, &idx) catch return 1;
        const subject = readBytes(input, &idx, subject_len) catch return 1;
        const poster_len = readU32(input, &idx) catch return 1;
        _ = readBytes(input, &idx, poster_len) catch return 1;
        const date_len = readU32(input, &idx) catch return 1;
        _ = readBytes(input, &idx, date_len) catch return 1;
        const size_len = readU32(input, &idx) catch return 1;
        const size_raw = readBytes(input, &idx, size_len) catch return 1;
        const message_len = readU32(input, &idx) catch return 1;
        _ = readBytes(input, &idx, message_len) catch return 1;

        const size_value = parseSize(size_raw);
        var flags: u32 = 0;
        if (hasNzb(subject)) flags |= FLAG_NZB;

        const output = @as([*]Result, @ptrFromInt(out_ptr));
        output[out_index] = Result{ .size = size_value, .flags = flags };
    }
    return 0;
}

pub export fn parse_tag_mask(in_ptr: usize, in_len: usize) u64 {
    if (in_ptr == 0 or in_len == 0) return 0;
    const input = @as([*]const u8, @ptrFromInt(in_ptr))[0..in_len];
    return tagMask(input);
}
