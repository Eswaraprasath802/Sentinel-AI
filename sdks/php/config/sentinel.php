<?php
/**
 * config/sentinel.php
 * Publish with: php artisan vendor:publish --tag=sentinel
 */

return [
    // URL of your running Sentinel Agent Server
    "server_url" => env("SENTINEL_URL", "http://localhost:8000"),

    // Your app name (shows in alerts)
    "app_name"   => env("APP_NAME", "LaravelApp"),
];
