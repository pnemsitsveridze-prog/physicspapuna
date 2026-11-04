# Minimal static file server (no Python/Node required). Usage: powershell -File serve.ps1 [-Port 8000]
param([int]$Port = 8000)
$root = $PSScriptRoot
$mime = @{ '.html'='text/html; charset=utf-8'; '.json'='application/json; charset=utf-8'; '.png'='image/png'; '.js'='text/javascript'; '.css'='text/css' }
$l = New-Object System.Net.HttpListener
$l.Prefixes.Add("http://localhost:$Port/")
$l.Start()
Write-Host "Serving $root at http://localhost:$Port/"
while ($l.IsListening) {
  $c = $l.GetContext()
  $rel = [Uri]::UnescapeDataString($c.Request.Url.AbsolutePath.TrimStart('/'))
  if ($rel -eq '') { $rel = 'index.html' }
  $p = Join-Path $root $rel
  if ((Test-Path $p -PathType Leaf) -and ($p.StartsWith($root))) {
    $b = [IO.File]::ReadAllBytes($p)
    $c.Response.ContentType = $mime[[IO.Path]::GetExtension($p).ToLower()]
    if (-not $c.Response.ContentType) { $c.Response.ContentType = 'application/octet-stream' }
    $c.Response.ContentLength64 = $b.Length
    if ($c.Request.HttpMethod -ne 'HEAD') {
      $c.Response.OutputStream.Write($b, 0, $b.Length)
    }
  } else { $c.Response.StatusCode = 404 }
  $c.Response.Close()
}
