// Claude Code statusLine 연동. WinUI 의존 없음 → 테스트 프로젝트가 직접 컴파일한다.
// Claude Code가 응답마다 statusLine 명령에 넘기는 JSON(rate_limits 포함)을 파일로 받아 API 조회 없이 즉시 반영한다.
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace UsageWidget;

public static class ClaudeLink
{
    public const string LiveName = "claude-live.json";
    public static string LivePath => Path.Combine(Config.Dir, LiveName);
    static string PrevPath => Path.Combine(Config.Dir, "statusline-prev.json");

    public static string SettingsPath =>
        Path.Combine(Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR") is { Length: > 0 } d ? d
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude"), "settings.json");

    static string Quote(string s) => "'" + s.Replace("'", "'\\''") + "'";

    /// statusLine은 Windows에서도 Git Bash로 실행된다. rate_limits가 있을 때만 저장한다:
    /// 새 세션은 첫 응답 전까지 rate_limits가 없어서, 그대로 쓰면 다른 세션의 값을 지운다.
    /// 기존 명령(prev)이 있으면 같은 입력을 넘기고 그 출력을 그대로 표시한다.
    public static string BuildCommand(string? prev, string livePath)
    {
        var p = livePath.Replace('\\', '/');
        var cmd = $"input=$(cat); case \"$input\" in *'\"rate_limits\"'*) printf '%s' \"$input\" > {Quote(p + ".tmp")} && mv -f {Quote(p + ".tmp")} {Quote(p)};; esac";
        return string.IsNullOrWhiteSpace(prev) ? cmd : $"{cmd}; printf '%s' \"$input\" | ( {prev} )";
    }

    public static bool IsLinked(string? command) => command?.Contains(LiveName) == true;

    static readonly JsonSerializerOptions WriteOpts = new() { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
    static readonly JsonDocumentOptions ReadOpts = new() { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true };

    static JsonObject LoadSettings(string path) =>
        File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8), documentOptions: ReadOpts) as JsonObject
                            ?? throw new JsonException("settings.json이 객체가 아님")
                          : new JsonObject();

    static string? CommandOf(JsonObject root) =>
        root["statusLine"] is JsonObject sl && sl["command"] is JsonValue v && v.TryGetValue(out string? c) ? c : null;

    static void SaveSettings(string path, JsonObject root)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (File.Exists(path)) File.Copy(path, path + ".usagewidget.bak", overwrite: true); // 사용자 설정이므로 되돌릴 수 있게
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, root.ToJsonString(WriteOpts), new UTF8Encoding(false));
        File.Move(tmp, path, overwrite: true);
    }

    public static bool IsEnabled(string settingsPath)
    {
        try { return IsLinked(CommandOf(LoadSettings(settingsPath))); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return false; }
    }

    /// 켜기/끄기. 실패하면 사유, 성공하면 null. settings.json을 읽지 못하면 건드리지 않는다.
    public static string? SetEnabled(string settingsPath, bool on)
    {
        try
        {
            var root = LoadSettings(settingsPath);
            if (IsLinked(CommandOf(root)) == on) return null;
            if (on)
            {
                var prev = root["statusLine"]?.DeepClone();
                Directory.CreateDirectory(Config.Dir);
                File.WriteAllText(PrevPath, prev?.ToJsonString() ?? "null", Encoding.UTF8);
                // 기존 설정(padding, refreshInterval 등)은 두고 명령만 감싼다
                var sl = prev as JsonObject ?? new JsonObject();
                sl["type"] = "command";
                sl["command"] = BuildCommand(CommandOf(root), LivePath);
                root["statusLine"] = sl;
            }
            else
            {
                var prev = File.Exists(PrevPath) ? JsonNode.Parse(File.ReadAllText(PrevPath, Encoding.UTF8)) : null;
                if (prev == null) root.Remove("statusLine");
                else root["statusLine"] = prev;
            }
            SaveSettings(settingsPath, root);
            return null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException)
        {
            return $"Claude Code 설정 변경 실패: {e.Message}";
        }
    }

    /// statusLine 입력 JSON → Usage. rate_limits가 없으면 null.
    /// Claude Code는 리셋 시각이 지난 창을 빼고 보낸다 → 빠진 창은 0%.
    public static Usage? Parse(JsonNode? data)
    {
        if (data is not JsonObject o || o["rate_limits"] is not JsonObject rl || rl.Count == 0) return null;
        UsageWindow W(string key) => rl[key] is JsonObject w
            ? new(UsageService.Pct(w["used_percentage"]), UsageService.ParseTime(w["resets_at"]))
            : new(0.0, null);
        return new(W("five_hour"), W("seven_day"));
    }

    /// 최근 MinInterval 안에 갱신된 값만 쓴다. 오래됐으면 null → API 조회로 넘어간다.
    public static AgentResult? ReadLive(DateTimeOffset now)
    {
        try
        {
            var f = new FileInfo(LivePath);
            if (!f.Exists || now - f.LastWriteTimeUtc > TimeSpan.FromSeconds(UsageService.MinInterval)) return null;
            return Parse(JsonNode.Parse(File.ReadAllText(f.FullName, Encoding.UTF8))) is { } u
                ? new(Usage: UsageService.ExpirePassed(u, now)) : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return null; }
    }
}
