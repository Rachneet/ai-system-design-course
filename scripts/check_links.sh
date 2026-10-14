#!/bin/sh
# usage: check_links.sh <file-with-urls>  -> prints "<status> <url>"
check() {
  code=$(curl -s -o /dev/null -L --max-time 20 -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/126 Safari/537.36" -w "%{http_code}" "$1")
  echo "$code $1"
}
export -f check 2>/dev/null
while read -r u; do [ -n "$u" ] && check "$u" & 
  while [ "$(jobs -r | wc -l)" -ge 24 ]; do sleep 0.2; done
done < "$1"
wait
