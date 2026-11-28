$ErrorActionPreference = 'Stop'
$project = 'repobrain-demo-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$gateway = "$project-gateway"
$compose = @('-p', $project, '-f', 'compose.test.yaml', '-f', 'compose.frontend-test.yaml')
$repo = (Resolve-Path .).Path
$tls = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) $project)
$env:REPOBRAIN_DEMO_FIXTURE_PASSWORD = [guid]::NewGuid().ToString('N')
function Docker-Checked {
    & docker @args
    if ($LASTEXITCODE) { throw 'Docker fixture command failed' }
}
function Assert-Status {
    param([int]$Expected, [string]$Path, [string[]]$Options = @())
    $status = & curl.exe --silent --show-error --max-time 10 --cacert $ca -o $nullDevice -w '%{http_code}' @Options "$base$Path"
    if ($LASTEXITCODE -or $status -ne "$Expected") {
        throw "Expected HTTP $Expected for $Path, got $status"
    }
}
try {
    Docker-Checked compose @compose up -d --build --wait backend
    foreach ($service in @('backend', 'test-db')) {
        $id = Docker-Checked compose @compose ps -q $service
        $ports = Docker-Checked inspect --format '{{json .HostConfig.PortBindings}}' $id
        if ($ports -notin @('null', '{}')) { throw "$service has a published port" }
    }
    Docker-Checked compose @compose build frontend
    Docker-Checked run --rm --network none -e REPOBRAIN_DEMO_FIXTURE_PASSWORD -v "${tls}:/fixture" -v "$repo/tests/demo_tls_fixture.py:/probe.py:ro" "$project-backend" python /probe.py
    Docker-Checked run --rm -d --name $gateway --network "${project}_default" -p '127.0.0.1::8443' --read-only --tmpfs /tmp --security-opt no-new-privileges --memory 128m --pids-limit 64 -v "${tls}:/run/demo:ro" -v "$repo/docs/examples/private-demo.nginx.conf:/etc/nginx/nginx.conf:ro" "$project-frontend"
    $listener = Docker-Checked port $gateway 8443/tcp
    if ($listener -notmatch '^127\.0\.0\.1:(\d+)$') { throw 'Gateway is not loopback-only' }
    $base = "https://localhost:$($Matches[1])"
    $ca = Join-Path $tls 'cert.pem'
    $nullDevice = if ($IsWindows) { 'NUL' } else { '/dev/null' }
    $id = '9bdaf39e-b9e0-4acf-89a5-0bfcdda66f53'
    $auth = @('--user', "demo:$env:REPOBRAIN_DEMO_FIXTURE_PASSWORD")
    Assert-Status 401 '/'
    Assert-Status 401 "/api/v1/snapshots/$id/graph"
    Assert-Status 401 '/' @('--user', 'demo:wrong-fixture-password')
    Assert-Status 200 "/snapshots/$id/overview" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/graph" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/source?path=reader.py" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/search/lexical?q=read_file" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/search/vector?q=read_file" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/search/hybrid?q=read_file" $auth
    Assert-Status 200 "/api/v1/snapshots/$id/search/graph-enhanced?q=read_file" $auth
    Assert-Status 403 "/api/v1/snapshots/$id/answer" $auth
    Assert-Status 405 '/api/v1/repositories/ingestions' ($auth + @('-X', 'POST'))
    Assert-Status 405 '/api/v1/workspace/account' ($auth + @('-X', 'DELETE'))
    Write-Output 'Private TLS smoke passed: authentication, all four search modes, graph, source, and write denial.'
} finally {
    & docker stop $gateway 2>$null | Out-Null
    & docker compose @compose down
    foreach ($file in @('cert.pem', 'key.pem', 'users')) {
        $path = Join-Path $tls $file
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    }
    Remove-Item -LiteralPath $tls
    Remove-Item Env:REPOBRAIN_DEMO_FIXTURE_PASSWORD
}
