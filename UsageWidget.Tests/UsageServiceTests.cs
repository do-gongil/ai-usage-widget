// UsageService / Settings 단위 테스트 (네트워크·UI 불필요).
using System.Text.Json.Nodes;
using UsageWidget;
using Xunit;
using S = UsageWidget.UsageService;

public class UsageServiceTests
{
    static JsonNode? J(string s) => JsonNode.Parse(s);
    static Usage U(double? p5, double? pw = null) => new(new(p5, null), new(pw, null));
    static AgentResult Ok(double? p5, double? pw = null) => new(Usage: U(p5, pw));
    static Dictionary<string, AgentResult> D(params (string, AgentResult)[] kv) => kv.ToDictionary(p => p.Item1, p => p.Item2);

    [Fact]
    public void ClaudeParse()
    {
        const string data = """
            {"five_hour":{"utilization":42.0,"resets_at":"2026-09-23T09:59:59.879814+00:00"},
             "seven_day":{"utilization":26.0,"resets_at":"2026-09-27T23:59:59+00:00"}}
            """;
        var u = S.ParseClaudeUsage(J(data));
        Assert.Equal(42.0, u.FiveHour.Pct);
        Assert.Equal(9, u.FiveHour.Reset!.Value.UtcDateTime.Hour);
        Assert.Equal(26.0, u.Weekly.Pct);
        // 키 누락·null
        Assert.Equal(U(null), S.ParseClaudeUsage(J("""{"five_hour":null}""")));
        Assert.Equal(U(null), S.ParseClaudeUsage(null));
        // 새 형식: legacy 키 없이 limits[]만. 모델 scope 항목은 무시
        const string limits = """
            [{"kind":"weekly_all","percent":30,"resets_at":"2026-09-27T23:59:59Z","scope":{"model":{"id":"opus"}}},
             {"kind":"session","percent":55,"resets_at":"2026-09-23T09:00:00Z"},
             {"kind":"weekly_all","utilization":12,"resets_at":"2026-09-27T23:59:59Z","scope":null}]
            """;
        u = S.ParseClaudeUsage(J("""{"limits":""" + limits + "}"));
        Assert.Equal(55.0, u.FiveHour.Pct);
        Assert.Equal(9, u.FiveHour.Reset!.Value.UtcDateTime.Hour);
        Assert.Equal(12.0, u.Weekly.Pct);
        // legacy 키가 있으면 그쪽 우선
        var both = J(data)!.AsObject();
        both["limits"] = J(limits);
        Assert.Equal(42.0, S.ParseClaudeUsage(both).FiveHour.Pct);
        Assert.Equal(default, S.ParseClaudeUsage(J("""{"limits":"bad"}""")).Weekly);
    }

    [Fact]
    public void CodexParse()
    {
        const string line = """{"timestamp":"2026-09-23T05:00:00Z","type":"event_msg","payload":{"type":"token_count","info":null,"rate_limits":{"primary":{"used_percent":12.5,"window_minutes":300,"resets_in_seconds":3600},"secondary":{"used_percent":3,"resets_at":1790000000}}}}""";
        var u = S.ParseCodexLine(line)!;
        Assert.Equal(12.5, u.FiveHour.Pct);
        Assert.Equal(6, u.FiveHour.Reset!.Value.UtcDateTime.Hour);
        Assert.Equal(3.0, u.Weekly.Pct);
        Assert.NotNull(u.Weekly.Reset);
        Assert.Null(S.ParseCodexLine("""{"payload":{"type":"agent_message"}}"""));
        Assert.Null(S.ParseCodexLine("""{"payload":{"type":"token_count"}}""")); // rate_limits 없음
        Assert.Null(S.ParseCodexLine("not json"));
        Assert.Null(S.ParseCodexLine("[1,2]"));
    }

    [Fact]
    public void Colors()
    {
        Assert.Equal(S.ColorUnknown, S.ColorFor(null));
        Assert.Equal(S.ColorOk, S.ColorFor(59.9));
        Assert.Equal(S.ColorWarn, S.ColorFor(60));
        Assert.Equal(S.ColorWarn, S.ColorFor(79.9));
        Assert.Equal(S.ColorCrit, S.ColorFor(80));
    }

    [Fact]
    public void IconStatePriority()
    {
        var none = D();
        var err = new AgentResult(Error: "오프라인");
        Assert.Equal((42.0, false), S.IconState(D(("claude", Ok(42)), ("codex", Ok(10))), none));
        Assert.Equal((10.0, false), S.IconState(D(("codex", Ok(10))), none));
        Assert.Equal(((double?)null, true), S.IconState(D(("claude", err), ("codex", Ok(10))), none));
        Assert.Equal((33.0, true), S.IconState(D(("claude", err)), D(("claude", Ok(33))))); // 실패 시 직전 값을 회색으로
        Assert.Equal(((double?)null, true), S.IconState(none, none));
        var both = Ok(42, 71);
        Assert.Equal((71.0, false), S.IconState(D(("claude", both)), none, "weekly"));
        Assert.Equal((71.0, true), S.IconState(D(("claude", err)), D(("claude", both)), "weekly"));
    }

    [Fact]
    public void IconText() =>
        Assert.Equal(new[] { "?", "5", "42", "99", "!" }, new double?[] { null, 5, 42.4, 99.6, 100 }.Select(S.IconText));

    [Fact]
    public void RetryDelay()
    {
        Assert.Equal(30, S.RetryDelay("30", 0));
        Assert.Equal(120, S.RetryDelay("0", 0)); // Retry-After: 0 은 무시하고 백오프
        Assert.Equal(240, S.RetryDelay(null, 120));
        Assert.Equal(S.MaxBackoff, S.RetryDelay(null, 480));
        Assert.Equal(S.MaxBackoff, S.RetryDelay("99999", 0));
    }

    [Fact]
    public void ExpirePassed()
    {
        var now = new DateTimeOffset(2026, 9, 23, 12, 0, 0, TimeSpan.Zero);
        var u = new Usage(new(50, now.AddMinutes(-1)), new(20, now.AddDays(1)));
        var o = S.ExpirePassed(u, now);
        Assert.Equal(new UsageWindow(0.0, null), o.FiveHour);
        Assert.Equal(u.Weekly, o.Weekly);
    }

    [Fact]
    public void LastCacheRoundtrip()
    {
        var future = DateTimeOffset.UtcNow.AddHours(2);
        var past = DateTimeOffset.UtcNow.AddMinutes(-1);
        var orig = Config.Dir;
        Config.Dir = Directory.CreateTempSubdirectory().FullName;
        try
        {
            Assert.Empty(Config.LoadLast()); // 파일 없음
            Config.SaveLast(D(("claude", new AgentResult(Usage: new(new(42, past), new(27, future))))));
            var got = Config.LoadLast()["claude"].Usage!;
            Assert.Equal(new UsageWindow(0.0, null), got.FiveHour); // 리셋 지난 값은 0%
            Assert.Equal(27.0, got.Weekly.Pct);
            Assert.Equal(future, got.Weekly.Reset);
            File.WriteAllText(Path.Combine(Config.Dir, "last.json"), "{broken");
            Assert.Empty(Config.LoadLast());
        }
        finally { Config.Dir = orig; }
    }

    [Fact]
    public void ConfigWithoutPipKeys()
    {
        var orig = Config.Dir;
        Config.Dir = Directory.CreateTempSubdirectory().FullName;
        try
        {
            // 예전 형식 설정 (pip 키 없음, interval 너무 짧음)
            File.WriteAllText(Path.Combine(Config.Dir, "config.json"),
                """{"agents":{"claude":true,"codex":false},"interval":60,"view":"weekly"}""");
            var c = Config.Load();
            Assert.True(c.Claude);
            Assert.False(c.Codex);
            Assert.Equal(S.MinInterval, c.Interval);
            Assert.Equal("weekly", c.View);
            Assert.True(c.PipVisible);
            c.PipRect = [1, 2, 300, 150];
            c.Save();
            Assert.Equal(new[] { 1, 2, 300, 150 }, Config.Load().PipRect);
        }
        finally { Config.Dir = orig; }
    }

    [Fact]
    public void CodexTailRead()
    {
        const string line = """{"payload":{"type":"token_count","rate_limits":{"primary":{"used_percent":77},"secondary":{"used_percent":5}}}}""";
        var orig = S.CodexHome;
        S.CodexHome = Directory.CreateTempSubdirectory().FullName;
        try
        {
            var f = Path.Combine(S.CodexHome, "sessions", "2026", "rollout.jsonl");
            Directory.CreateDirectory(Path.GetDirectoryName(f)!);
            // 앞부분을 tail 크기보다 크게 채워 잘린 첫 줄이 생기도록
            File.WriteAllText(f, string.Concat(Enumerable.Repeat(new string('x', 1000) + "\n", 400)) + line + "\n");
            Assert.Equal(77.0, S.ReadCodex().Usage!.FiveHour.Pct);
        }
        finally { S.CodexHome = orig; }
    }

    [Fact]
    public void Tooltip()
    {
        var ok = Ok(42, 18);
        Assert.Equal("Claude 5h 42% 주 18%", S.FormatLine("Claude", ok));
        Assert.Equal("Claude: 오프라인 (직전 5h 42%)", S.FormatLine("Claude", new(Error: "오프라인"), ok));
        Assert.Equal(S.TooltipMax, S.BuildTooltip([new string('x', 300)]).Length);
    }
}
