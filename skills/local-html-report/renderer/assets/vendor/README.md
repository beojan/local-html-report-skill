# Locally vendored frontend assets

`local-report update-assets` downloads Bootstrap 5 and Font Awesome Free into
this directory from jsDelivr. The exact resolved download URLs are recorded in
`manifest.json`. Generated reports use only these local copies; they never load
frontend assets from the network.

The selected Iosevka variants are vendored separately in `../fonts/`, sourced
from the local custom font installation. They are deliberately not replaced by
this updater.
