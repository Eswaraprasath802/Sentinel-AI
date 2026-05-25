<?php
/**
 * SentinelServiceProvider.php
 * Auto-registers Sentinel in Laravel.
 *
 * Add to config/app.php providers array:
 *   Sentinel\SentinelServiceProvider::class,
 */

namespace Sentinel;

use Illuminate\Support\ServiceProvider;

class SentinelServiceProvider extends ServiceProvider
{
    public function boot(): void
    {
        // Auto-boot Sentinel when Laravel starts
        Sentinel::boot(
            serverUrl: config("sentinel.server_url", env("SENTINEL_URL", "http://localhost:8000")),
            appName:   config("sentinel.app_name",   env("APP_NAME",     "LaravelApp"))
        );
    }

    public function register(): void
    {
        // Merge default config
        $this->mergeConfigFrom(__DIR__ . "/../config/sentinel.php", "sentinel");
    }
}
