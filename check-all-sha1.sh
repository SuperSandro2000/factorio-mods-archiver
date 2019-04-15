#!/bin/bash
set -exou pipefail
find -name "*.sha1" | xargs -I % dos2unix -q "%" >/dev/null
find -name "*.sha1" | xargs -I % sh -c "cd \"\$(dirname \"%\")\" && sha1sum -c \"./\$(basename \"%\")\" > /dev/null || echo fail %"
echo "No errors found"
