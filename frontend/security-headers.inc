# ---------------------------------------------------------------------------
# Security headers for HTML responses.
#
# Kept in an include because nginx's `add_header` does not inherit into a
# `location` that declares its own — so every block that adds a header must
# repeat the whole set, and one copy is easier to keep correct than three.
#
# The CSP is written against what the bundle actually does:
#
#   script-src 'self'   — Vite emits external, hashed scripts; no inline code.
#   style-src  adds 'unsafe-inline' — unavoidable. React Flow and Motion both
#              set element.style directly for transforms, which the style-src
#              directive governs. Nonces cannot cover style *attributes*, so
#              the honest options are 'unsafe-inline' or no animation.
#   img-src    data: — device icons and the exported topology thumbnail are
#              inlined data URIs.
#   connect-src 'self' — the API is same-origin by design; nothing else is
#              contacted, so an exfiltration attempt has nowhere to send to.
# ---------------------------------------------------------------------------

add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests" always;

add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Cross-Origin-Opener-Policy "same-origin" always;
add_header Permissions-Policy "accelerometer=(), autoplay=(), camera=(), display-capture=(), encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), usb=()" always;

# Enable once TLS terminates here. Behind Azure Front Door or another edge that
# already sends HSTS, leave it commented — two copies is a misconfiguration.
# add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
