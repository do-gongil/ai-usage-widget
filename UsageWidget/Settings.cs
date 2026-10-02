// %APPDATA%\UsageTray\config.json / last.json
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace UsageWidget;

public sealed class Config
{
    public bool Claude { get; set; }
    public bool Codex { get; set; }
    public int Interval { get; set; } = UsageService.MinInterval;
    public string View { get; set; } = "five_hour";
    public bool PipVisible { get; set; } = true;
    public int[]? PipRect { get; set; } // x, y, w, h (물리 픽셀)
    public bool PipTopMost { get; set; } = true;
    public string? PipColor { get; set; } // "#RRGGBB", null = 기본(Mica)
    public int PipOpacity { get; set; } = 100; // % (MinOpacity~100)
    public const int MinOpacity = 30; // 너무 투명하면 창을 잃어버린다
    public bool PipMini { get; set; } // 미니 모드: 상단 행 없이 작업 표시줄 높이
    public int[]? PipMiniRect { get; set; } // 미니 모드 창 위치·크기 (일반 창과 따로 기억)

    public static string Dir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), UsageService.AppName);
    static string ConfigPath => Path.Combine(Dir, "config.json");
    static string LastPath => Path.Combine(Dir, "last.json");

    public static Config Load()
    {
        try
        {
            var o = JsonNode.Parse(File.ReadAllText(ConfigPath, Encoding.UTF8))!.AsObject();
            var agents = o["agents"] as JsonObject;
            var pip = o["pip"] as JsonObject;
            static int[]? Rect(JsonNode? n) =>
                n is JsonArray a && a.Count == 4 ? a.Select(v => v!.GetValue<int>()).ToArray() : null;
            return new Config
            {
                Claude = agents?["claude"]?.GetValue<bool>() ?? false,
                Codex = agents?["codex"]?.GetValue<bool>() ?? false,
                // 상한: 너무 크면 Task.Delay가 예외를 던져 조회 루프가 멈춘다
                Interval = Math.Clamp(o["interval"]?.GetValue<int>() ?? UsageService.MinInterval, UsageService.MinInterval, MaxInterval),
                View = (string?)o["view"] == "weekly" ? "weekly" : "five_hour",
                PipVisible = pip?["visible"]?.GetValue<bool>() ?? true,
                PipRect = Rect(pip?["rect"]),
                PipMini = pip?["mini"]?.GetValue<bool>() ?? false,
                PipMiniRect = Rect(pip?["mini_rect"]),
                PipTopMost = pip?["topmost"]?.GetValue<bool>() ?? true,
                PipColor = pip?["color"] is JsonValue c && c.TryGetValue(out string? hex) && IsHex(hex) ? hex : null,
                PipOpacity = Math.Clamp(pip?["opacity"]?.GetValue<int>() ?? 100, MinOpacity, 100),
            };
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException
                                      or InvalidOperationException or FormatException or NullReferenceException)
        {
            var cfg = new Config
            {
                Claude = File.Exists(UsageService.ClaudeCredentials),
                Codex = Directory.Exists(UsageService.CodexHome),
            };
            cfg.Save();
            return cfg;
        }
    }

    public const int MaxInterval = 86400; // 1일

    /// 임시 파일에 다 쓴 뒤 교체: 쓰는 도중 꺼져도 기존 파일이 반쯤 잘린 채 남지 않는다
    static void WriteAtomic(string path, string text)
    {
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, text, Encoding.UTF8);
        File.Move(tmp, path, overwrite: true);
    }

    public static bool IsHex(string? s) =>
        s is { Length: 7 } && s[0] == '#' && s[1..].All(Uri.IsHexDigit);

    static JsonArray? Json(int[]? r) => r == null ? null : new JsonArray(r.Select(v => (JsonNode)v).ToArray());

    public void Save()
    {
        var o = new JsonObject
        {
            ["agents"] = new JsonObject { ["claude"] = Claude, ["codex"] = Codex },
            ["interval"] = Interval,
            ["view"] = View,
            ["pip"] = new JsonObject
            {
                ["visible"] = PipVisible,
                ["rect"] = Json(PipRect),
                ["mini"] = PipMini,
                ["mini_rect"] = Json(PipMiniRect),
                ["topmost"] = PipTopMost,
                ["color"] = PipColor,
                ["opacity"] = PipOpacity,
            },
        };
        try
        {
            Directory.CreateDirectory(Dir);
            WriteAtomic(ConfigPath, o.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { } // 설정 저장 실패로 앱이 죽지 않게
    }

    /// 마지막 성공 값 저장: 재시작 직후나 429 중에도 '?' 대신 직전 값을 보여주기 위함.
    public static void SaveLast(IReadOnlyDictionary<string, AgentResult> last)
    {
        static JsonArray W(UsageWindow w) => new(w.Pct, w.Reset?.ToString("o"));
        var o = new JsonObject();
        foreach (var (agent, r) in last)
            if (r.Usage is { } u)
                o[agent] = new JsonObject { ["five_hour"] = W(u.FiveHour), ["weekly"] = W(u.Weekly) };
        try
        {
            Directory.CreateDirectory(Dir);
            WriteAtomic(LastPath, o.ToJsonString());
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { } // 캐시일 뿐
    }

    public static Dictionary<string, AgentResult> LoadLast()
    {
        var result = new Dictionary<string, AgentResult>();
        try
        {
            if (JsonNode.Parse(File.ReadAllText(LastPath, Encoding.UTF8)) is not JsonObject data) return result;
            foreach (var agent in new[] { "claude", "codex" })
            {
                if (data[agent] is not JsonObject w || w["five_hour"] is not JsonArray f || w["weekly"] is not JsonArray k
                    || f.Count < 2 || k.Count < 2) continue;
                var u = new Usage(new(UsageService.Pct(f[0]), UsageService.ParseTime(f[1])),
                                  new(UsageService.Pct(k[0]), UsageService.ParseTime(k[1])));
                result[agent] = new(Usage: UsageService.ExpirePassed(u, DateTimeOffset.UtcNow));
            }
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { }
        return result;
    }
}
