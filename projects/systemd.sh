# Elixir definitions for systemd

list_tags_h()
{
    # tags that start with v and three digits
    echo "$tags" |
    grep -E '^v[0-9]{3}' |
    tac |
    sed -r 's/^(v[0-9])([0-9])(.*)$/\1xx \1\2x \1\2\3/'

    # tags before v100 are marked as 'old'
    echo "$tags" |
    grep -E '^v[0-9]{2}$' |
    tac |
    sed -r 's/^(v[0-9])([0-9])(.*)$/old \1x \1\2\3/'

    echo "$tags" |
    grep -E '^v[0-9]$' |
    tac |
    sed -r 's/^(v[0-9])$/old vx \1/'

    # tags that don't start with v seem to be more related to udev?
    # suggesting that systemd grew out of udev, but I don't know history of the project
    # currently marked as old-udev
    echo "$tags" |
    grep -v '^v' |
    tac |
    sed -r 's/^([0-9])([0-9])(.*)$/old-udev \1\2 \1\2\3/'
}
