cd ~/tiktok-live-recorder

USER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -user)
            USER="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [[ -n "$USER" ]]; then
    echo "$USER" > ~/tiktok/tk/user.txt
    uv run python src/main.py -user "$USER"
else
    echo "Usage: $0 -user <username>"
    exit 1
fi
