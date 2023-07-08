from subprocess import CompletedProcess
from internet_troubleshooter.speed_test import SpeedResult

test_json = """
{
   "type":"result",
   "timestamp":"2023-07-08T20:07:29Z",
   "ping":{
      "jitter":1.306,
      "latency":19.266,
      "low":17.387,
      "high":22.368
   },
   "download":{
      "bandwidth":7317857,
      "bytes":74558968,
      "elapsed":10610,
      "latency":{
         "iqm":58.422,
         "low":19.483,
         "high":283.500,
         "jitter":14.344
      }
   },
   "upload":{
      "bandwidth":2140150,
      "bytes":10269216,
      "elapsed":4807,
      "latency":{
         "iqm":72.092,
         "low":22.028,
         "high":311.506,
         "jitter":24.518
      }
   },
   "packetLoss":0,
   "isp":"MyISP",
   "interface":{
      "internalIp":"192.168.1.1",
      "name":"enp3s0",
      "macAddr":"AA:AA:AA:AA:AA:AA",
      "isVpn":false,
      "externalIp":"555.555.555.555"
   },
   "server":{
      "id":27863,
      "host":"speedtest-stemmons-tx.conterra.com",
      "port":8080,
      "name":"Conterra",
      "location":"Stemmons, TX",
      "country":"United States",
      "ip":"69.194.191.83"
   },
   "result":{
      "id":"555-555",
      "url":"https://www.speedtest.net/result/c/555-555",
      "persisted":true
   }
}
    """


def test_SpeedResult():
    x = SpeedResult(results=test_json)
    assert x.download == 58.542856
    assert x.upload == 17.1212
    assert x.latency == 19.266
