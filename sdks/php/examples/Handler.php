<?php
/**
 * app/Exceptions/Handler.php
 * Add Sentinel::report() here — just 1 line!
 */

namespace App\Exceptions;

use Illuminate\Foundation\Exceptions\Handler as ExceptionHandler;
use Throwable;
use Sentinel\Sentinel;  // ← Add this

class Handler extends ExceptionHandler
{
    public function register(): void
    {
        $this->reportable(function (Throwable $e) {

            // ← Add this ONE line — that's it!
            Sentinel::report($e, [
                "endpoint" => request()->path(),
                "method"   => request()->method(),
            ]);

        });
    }
}
