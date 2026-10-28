// ClaudeLink 단위 테스트: settings.json 켜기/끄기 왕복, statusLine 명령 실제 실행(Git Bash).
using System.Diagnostics;
using System.Text.Json.Nodes;
using UsageWidget;
using Xunit;

public class ClaudeLinkTests
{
    const string Sample = """{"model":{"display_name":"Opus"},"rate_limits":{"five_hour":{"used_percentage":23.5,"resets_at":1738425600}}}""";

    [Fact]
    public void Parse()
    {
        var u = ClaudeLink.Parse(JsonNode.Parse(Sample))!;
        Assert.Equal(23.5, u.FiveHour.Pct);
        Assert.Equal(DateTimeOffset.FromUnixTimeSeconds(1738425600), u.FiveHour.Reset);
        Assert.Equal(0.0, u.Weekly.Pct); // 리셋이 지나 빠진 창
        Assert.Null(ClaudeLink.Parse(JsonNode.Parse("""{"model":{}}"""))); // 첫 응답 전
    }

    [Fact]
    public void EnableDisableRoundTripKeepsPrevious()
    {
        var orig = Config.Dir;
        Config.Dir = Directory.CreateTempSubdirectory().FullName;
        try
        {
            var settings = Path.Combine(Config.Dir, "settings.json");
            File.WriteAllText(settings, """{"model":"opus","statusLine":{"type":"command","command":"echo hud","padding":1}}""");
            Assert.Null(ClaudeLink.SetEnabled(settings, true));
            Assert.True(ClaudeLink.IsEnabled(settings));
            var sl = JsonNode.Parse(File.ReadAllText(settings))!["statusLine"]!;
            Assert.Contains("( echo hud )", (string)sl["command"]!); // 기존 명령을 이어서 실행
            Assert.Equal(1, (int)sl["padding"]!);
            Assert.Null(ClaudeLink.SetEnabled(settings, true)); // 두 번 켜도 중복으로 감싸지 않음
            Assert.Null(ClaudeLink.SetEnabled(settings, false));
            var back = JsonNode.Parse(File.ReadAllText(settings))!;
            Assert.Equal("echo hud", (string)back["statusLine"]!["command"]!);
            Assert.Equal("opus", (string)back["model"]!);
        }
        finally { Config.Dir = orig; }
    }

    static string? GitBash() =>
        new[] { @"C:\Program Files\Git\bin\bash.exe", @"C:\Program Files (x86)\Git\bin\bash.exe" }.FirstOrDefault(File.Exists);

    static string Run(string bash, string command, string stdin)
    {
        var psi = new ProcessStartInfo(bash) { RedirectStandardInput = true, RedirectStandardOutput = true, UseShellExecute = false };
        psi.ArgumentList.Add("-c");
        psi.ArgumentList.Add(command);
        using var p = Process.Start(psi)!;
        p.StandardInput.Write(stdin);
        p.StandardInput.Close();
        var output = p.StandardOutput.ReadToEnd();
        p.WaitForExit();
        return output;
    }

    [Fact]
    public void CommandWritesLiveFileAndChainsPrevious()
    {
        if (GitBash() is not { } bash) return; // Git Bash 없는 환경은 건너뜀
        var dir = Directory.CreateTempSubdirectory().FullName;
        var live = Path.Combine(dir, ClaudeLink.LiveName);
        var cmd = ClaudeLink.BuildCommand("exec cat", live);

        Assert.Equal(Sample, Run(bash, cmd, Sample)); // 기존 명령은 같은 입력을 받는다
        Assert.Equal(Sample, File.ReadAllText(live));
        Run(bash, cmd, """{"model":{}}""");
        Assert.Equal(Sample, File.ReadAllText(live)); // rate_limits 없는 입력은 덮지 않음
        Assert.False(File.Exists(live + ".tmp"));
    }
}
