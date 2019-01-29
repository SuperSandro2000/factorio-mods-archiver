#!/bin/bash
find -name "*.sha1" | xargs -I % sh -c "cd \"\$(dirname \"%\")\" && sha1sum -c \"\$(basename \"%\")\" > /dev/null || echo fail %"
