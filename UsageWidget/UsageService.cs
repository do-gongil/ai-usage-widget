// 사용량 조회/파싱 로직. WinUI 의존 없음 → 테스트 프로젝트가 이 파일을 직접 컴파일한다.
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace UsageWidget;

public readonly record struct UsageWindow(double? Pct, DateTimeOffset? Reset);

public sealed record Usage(UsageWindow FiveHour, UsageWindow Weekly)
{
    public UsageWindow Get(string view) => view == "weekly" ? Weekly : FiveHour;
}

/// RetryAfter != null 이면 429 (헤더 없으면 빈 문자열).
public sealed record AgentResult(Usage? Usage = null, string? Error = null,
                                 string? RetryAfter = null, DateTimeOffset? LastUsed = null);

public static class UsageService
{
    public const string AppName = "UsageTray";
    public const string UsageUrl = "https://api.anthropic.com/api/oauth/usage";
    public const int MinInterval = 300; // usage API 제한 창이 약 5분: 더 짧으면 429
    public const int MaxBackoff = 600;
    public const int CodexTailBytes = 256 * 1024;
    public const int TooltipMax = 127; // Windows NOTIFYICONDATA szTip 제한

    public const string ColorOk = "#2f9e5b", ColorWarn = "#d98a12", ColorCrit = "#d33b3b", ColorUnknown = "#7a8090";

    static readonly string Home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    public static string ClaudeCredentials = Path.Combine(Home, ".claude", ".credentials.json");
    public static string CodexHome = Environment.GetEnvironmentVariable("CODEX_HOME") is { Length: > 0 } c
        ? c : Path.Combine(Home, ".codex");

    // ---------- 파싱 ----------

    public static double? Pct(JsonNode? value)
    {
        if (value is not JsonValue v) return null;
        double d;
        if (v.TryGetValue(out double dd)) d = dd;
        else if (v.TryGetValue(out string? s) && double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var ds)) d = ds;
        else return null;
        return double.IsNaN(d) ? null : Math.Clamp(d, 0, 100);
    }

    /// ISO 문자열 또는 epoch 초 → DateTimeOffset. 실패 시 null.
    public static DateTimeOffset? ParseTime(JsonNode? value)
    {
        if (value is not JsonValue v) return null;
        try
        {
            if (v.TryGetValue(out double secs)) return DateTimeOffset.FromUnixTimeMilliseconds((long)(secs * 1000));
            if (v.TryGetValue(out string? s) &&
                DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var t))
                return t;
        }
        catch (ArgumentOutOfRangeException) { }
        return null;
    }

    static JsonNode? Field(JsonNode? node, string key) => node is JsonObject o ? o[key] : null;

    static bool IsFalsy(JsonNode? n) => n switch
    {
        null => true,
        JsonObject o => o.Count == 0,
        JsonArray a => a.Count == 0,
        JsonValue v => v.GetValueKind() == JsonValueKind.False || (v.TryGetValue(out string? s) && s.Length == 0),
        _ => false,
    };

    /// /api/oauth/usage 응답 → Usage
    public static Usage ParseClaudeUsage(JsonNode? data)
    {
        // 새 형식은 legacy 키를 뺄 수 있다: 모델 scope 없는 limits[] 항목으로 대체
        var unscoped = new Dictionary<string, JsonNode>();
        if (Field(data, "limits") is JsonArray limits)
            foreach (var l in limits)
                if (l is JsonObject lo && IsFalsy(lo["scope"]) && lo["kind"] is JsonValue k && k.TryGetValue(out string? kind))
                    unscoped[kind] = lo;

        UsageWindow Window(string key, string kind)
        {
            var w = Field(data, key) is JsonObject wo ? wo : unscoped.GetValueOrDefault(kind);
            var pct = w is JsonObject o && o.ContainsKey("utilization") ? o["utilization"] : Field(w, "percent");
            return new(Pct(pct), ParseTime(Field(w, "resets_at")));
        }
        return new(Window("five_hour", "session"), Window("seven_day", "weekly_all"));
    }

    /// rollout jsonl 한 줄 → Usage. token_count/rate_limits 가 아니면 null.
    public static Usage? ParseCodexLine(string line, DateTimeOffset? baseTime = null)
    {
        JsonNode? obj;
        try { obj = JsonNode.Parse(line); }
        catch (JsonException) { return null; }
        if (Field(obj, "payload") is not JsonObject payload) return null;
        if (payload["type"] is not JsonValue t || !t.TryGetValue(out string? type) || type != "token_count") return null;
        if (payload["rate_limits"] is not JsonObject limits) return null;
        var @base = ParseTime(Field(obj, "timestamp")) ?? baseTime;

        UsageWindow Window(string key)
        {
            var w = limits[key];
            var reset = ParseTime(Field(w, "resets_at"));
            if (reset == null && @base != null && Field(w, "resets_in_seconds") is JsonValue sv && sv.TryGetValue(out double secs))
                reset = @base.Value.AddSeconds(secs);
            return new(Pct(Field(w, "used_percent")), reset);
        }
        return new(Window("primary"), Window("secondary"));
    }

    /// 리셋 시각이 지난 창은 0%로 본다 (오래된 Codex 기록 대응).
    public static Usage ExpirePassed(Usage u, DateTimeOffset now)
    {
        UsageWindow E(UsageWindow w) => w.Reset is { } r && r <= now ? new(0.0, null) : w;
        return new(E(u.FiveHour), E(u.Weekly));
    }

    // ---------- 표시 ----------

    public static string ColorFor(double? pct) => pct switch
    {
        null => ColorUnknown,
        >= 80 => ColorCrit,
        >= 60 => ColorWarn,
        _ => ColorOk,
    };

    public static string FmtPct(double? pct) =>
        pct == null ? "--" : Math.Round(pct.Value, MidpointRounding.ToEven).ToString("0", CultureInfo.InvariantCulture) + "%";

    public static string FmtTime(DateTimeOffset? dt)
    {
        if (dt == null) return "";
        var local = dt.Value.ToLocalTime();
        return local.Date == DateTimeOffset.Now.Date ? local.ToString("HH:mm") : local.ToString("MM/dd HH:mm");
    }

    public static string IconText(double? pct) => pct switch
    {
        null => "?",
        >= 100 => "!", // 16px에 세 자리는 안 읽힘. 한도 소진은 '!'로 99%와 구분
        _ => Math.Min(99, (int)Math.Round(pct.Value, MidpointRounding.ToEven)).ToString(CultureInfo.InvariantCulture),
    };

    /// 툴팁 한 줄. 실패 시 마지막 성공 값(last)을 괄호로 덧붙인다.
    public static string FormatLine(string name, AgentResult result, AgentResult? last = null)
    {
        if (result.Error != null)
            return last?.Usage is { } lu ? $"{name}: {result.Error} (직전 5h {FmtPct(lu.FiveHour.Pct)})" : $"{name}: {result.Error}";
        var u = result.Usage!;
        var line = $"{name} 5h {FmtPct(u.FiveHour.Pct)} 주 {FmtPct(u.Weekly.Pct)}";
        if (u.FiveHour.Reset != null) line += $" ↻{FmtTime(u.FiveHour.Reset)}";
        if (result.LastUsed != null) line += $" ({FmtTime(result.LastUsed)} 기준)";
        return line;
    }

    public static string BuildTooltip(IList<string> lines)
    {
        var text = lines.Count == 0 ? "사용할 agent를 메뉴에서 선택하세요" : string.Join("\n", lines);
        return text.Length <= TooltipMax ? text : text[..(TooltipMax - 1)] + "…";
    }

    /// (아이콘 숫자, 오래된 값 여부). Claude 우선, 꺼져 있으면 Codex.
    /// 조회 실패 시 직전 성공 값을 회색으로, 직전 값도 없으면 (null, true).
    public static (double? Pct, bool Stale) IconState(IReadOnlyDictionary<string, AgentResult> results,
                                                     IReadOnlyDictionary<string, AgentResult> last, string view = "five_hour")
    {
        foreach (var agent in new[] { "claude", "codex" })
        {
            if (!results.TryGetValue(agent, out var r)) continue;
            if (r.Usage != null) return (r.Usage.Get(view).Pct, false);
            if (last.TryGetValue(agent, out var l) && l.Usage != null) return (l.Usage.Get(view).Pct, true);
            return (null, true);
        }
        return (null, true);
    }

    // ---------- 조회 ----------

    /// 429 대기 시간(초): Retry-After가 있으면 따르고, 없으면 120초부터 2배씩 늘려 최대 600초.
    public static int RetryDelay(string? retryAfter, int previous)
    {
        if (int.TryParse(retryAfter, out var s) && s > 0) return Math.Min(s, MaxBackoff);
        return Math.Min(Math.Max(previous * 2, 120), MaxBackoff);
    }

    // 리다이렉트를 따라가지 않는다: 다른 호스트로 Authorization 헤더가 넘어가지 않게.
    static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(10) };

    public static async Task<AgentResult> FetchClaudeAsync()
    {
        // ponytail: 토큰 갱신은 Claude Code에 맡긴다. 여기서 credentials 파일을 쓰면 로그인이 깨질 수 있다.
        string? token;
        try
        {
            var creds = JsonNode.Parse(await File.ReadAllTextAsync(ClaudeCredentials, Encoding.UTF8));
            token = Field(Field(creds, "claudeAiOauth"), "accessToken") is JsonValue tv && tv.TryGetValue(out string? s) ? s : null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { token = null; }
        if (string.IsNullOrEmpty(token)) return new(Error: "미로그인");

        using var req = new HttpRequestMessage(HttpMethod.Get, UsageUrl);
        req.Headers.TryAddWithoutValidation("Authorization", $"Bearer {token}");
        req.Headers.TryAddWithoutValidation("anthropic-beta", "oauth-2025-04-20");
        req.Headers.TryAddWithoutValidation("User-Agent", AppName);
        try
        {
            using var resp = await Http.SendAsync(req);
            if (resp.StatusCode == HttpStatusCode.Unauthorized) return new(Error: "토큰 만료 (Claude Code 실행 필요)");
            if (resp.StatusCode == HttpStatusCode.TooManyRequests)
            {
                var ra = resp.Headers.TryGetValues("Retry-After", out var v) ? v.FirstOrDefault() : null;
                return new(Error: "요청 제한, 잠시 후 재시도", RetryAfter: ra ?? "");
            }
            if (!resp.IsSuccessStatusCode) return new(Error: $"HTTP {(int)resp.StatusCode}");
            try { return new(Usage: ParseClaudeUsage(JsonNode.Parse(await resp.Content.ReadAsStringAsync()))); }
            catch (JsonException) { return new(Error: "응답 형식 오류"); }
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or IOException)
        {
            return new(Error: "오프라인");
        }
    }

    static List<string> ReadTailLines(string path)
    {
        using var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        f.Seek(Math.Max(0, f.Length - CodexTailBytes), SeekOrigin.Begin);
        using var r = new StreamReader(f, Encoding.UTF8);
        // 잘린 첫 줄은 JSON 파싱에 실패해 자연히 건너뛴다
        return r.ReadToEnd().Split('\n').Select(l => l.TrimEnd('\r')).ToList();
    }

    public static AgentResult ReadCodex()
    {
        List<FileInfo> files;
        try
        {
            files = new DirectoryInfo(Path.Combine(CodexHome, "sessions"))
                .EnumerateFiles("*.jsonl", SearchOption.AllDirectories)
                .OrderByDescending(f => f.LastWriteTimeUtc).Take(5).ToList();
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { files = []; }

        // ponytail: 최근 5개 파일의 끝 256KB만 본다. token_count가 그보다 앞에만 있으면 다음 파일로 넘어감.
        foreach (var file in files)
        {
            DateTimeOffset mtime;
            List<string> lines;
            try { mtime = file.LastWriteTimeUtc; lines = ReadTailLines(file.FullName); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { continue; }
            for (var i = lines.Count - 1; i >= 0; i--)
                if (ParseCodexLine(lines[i], mtime) is { } usage)
                    return new(Usage: ExpirePassed(usage, DateTimeOffset.UtcNow), LastUsed: mtime);
        }
        return new(Error: "기록 없음");
    }
}
