const std = @import("std");

const allocator = std.heap.wasm_allocator;
const Result = struct {
    size: u32,
    flags: u32,
};

const FLAG_NZB: u32 = 1;

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
