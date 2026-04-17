Monitore bus in real-time
`dbus-monitor "destination=ru.hackathon.CloudService"`

Send test method call
`dbus-send --session --print-reply --dest=ru.hackathon.CloudService /ru/hackathon/CloudService ru.hackathon.CloudService.HandleAction string:"upload" string:"/home/test.txt"`
