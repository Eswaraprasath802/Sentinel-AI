<?php
/**
 * Sentinel PHP SDK
 * Just 2 lines to add AI auto-healing to any Laravel app.
 *
 * Usage in app/Exceptions/Handler.php:
 *   use Sentinel\Sentinel;
 *   Sentinel::report($exception);
 */

namespace Sentinel;

class Sentinel
{
    private static ?self $instance = null;

    private string $serverUrl;
    private string $appName;
    private string $language  = "php";
    private string $framework = "laravel";

    public function __construct(
        string $serverUrl = "",
        string $appName   = "LaravelApp"
    ) {
        $this->serverUrl = $serverUrl ?: (getenv("SENTINEL_URL") ?: "http://localhost:8000");
        $this->appName   = $appName   ?: (getenv("SENTINEL_APP") ?: "LaravelApp");
    }

    /**
     * Boot Sentinel — call once in AppServiceProvider::boot()
     */
    public static function boot(
        string $serverUrl = "",
        string $appName   = "LaravelApp"
    ): self {
        self::$instance = new self($serverUrl, $appName);
        self::$instance->checkHealth();
        return self::$instance;
    }

    /**
     * Report an exception to the Sentinel Agent Server
     * Call this from app/Exceptions/Handler.php register() method
     */
    public static function report(\Throwable $exception, array $extra = []): void
    {
        if (!self::$instance) {
            self::boot();
        }
        self::$instance->send($exception, $extra);
    }

    /**
     * Send error to Sentinel Agent Server
     */
    private function send(\Throwable $e, array $extra = []): void
    {
        $payload = [
            "app_name"   => $this->appName,
            "language"   => $this->language,
            "framework"  => $this->framework,
            "error"      => $e->getMessage(),
            "error_type" => get_class($e),
            "traceback"  => $e->getTraceAsString(),
            "endpoint"   => $extra["endpoint"] ?? (
                isset($_SERVER["REQUEST_URI"]) ? $_SERVER["REQUEST_URI"] : "cli"
            ),
            "method"     => $extra["method"] ?? (
                isset($_SERVER["REQUEST_METHOD"]) ? $_SERVER["REQUEST_METHOD"] : "CLI"
            ),
            "timestamp"  => (new \DateTime())->format(\DateTime::ISO8601),
            "extra"      => $extra
        ];

        // Fire and forget — don't block the response
        $this->fireAndForget($payload);
    }

    /**
     * Send HTTP POST without blocking (async via curl)
     */
    private function fireAndForget(array $payload): void
    {
        $json = json_encode($payload);
        $url  = rtrim($this->serverUrl, "/") . "/report";

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $json,
            CURLOPT_HTTPHEADER     => ["Content-Type: application/json"],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 3,       // 3 second timeout max
            CURLOPT_CONNECTTIMEOUT => 2,
        ]);
        curl_exec($ch);
        curl_close($ch);
    }

    /**
     * Health check — verify agent server is running
     */
    public function checkHealth(): bool
    {
        $url = rtrim($this->serverUrl, "/") . "/health";
        $ch  = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 3,
        ]);
        $response = curl_exec($ch);
        $code     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $ok = $code === 200;
        if ($ok) {
            echo "[Sentinel] ✅ Agent Server connected — AI monitoring active\n";
        } else {
            echo "[Sentinel] ⚠️  Agent Server not reachable at {$this->serverUrl}\n";
        }
        return $ok;
    }
}
