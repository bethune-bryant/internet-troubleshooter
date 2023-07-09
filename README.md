# Internet Troubleshooter

[![codecov](https://codecov.io/github/bethune-bryant/internet-troubleshooter/branch/main/graph/badge.svg?token=JN4VXWSJNI)](https://codecov.io/github/bethune-bryant/internet-troubleshooter)

## Overview



## Getting Started

To get started you can setup a Python virtual environment and use pip to install the troubleshooter.

```shell
$ sudo apt install python3.10-venv
$ python3 -m venv ./my_env
$ source ./my_env/bin/activate
$ pip install git+https://github.com/bethune-bryant/internet-troubleshooter.git
$ checkinternet run
WARNING: Script not run as root, unable to flood ping. Packet loss may not be accurate
Packet Loss: 0.00%
Download:    58.74Mbps
Upload:      17.19Mbps
Latency:     15.73ms
```

> For a more accurate packet loss, run checkinternet as `root`.

## Tracking and Displaying Statistics

The `checkinternet` script supports logging results to a yaml file and then displaying them to either the console or an html file.

```shell
$ checkinternet run --yaml_file troubleshooting.yaml
...
$ checkinternet display --yaml_file /home/brnelson/troubleshooting.yaml
Download:
  Mean: 57.97Mbps
  Variance: 6.69Mbps
  Min: 48.66Mbps
  Max: 59.48Mbps

Upload:
  Mean: 17.33Mbps
  Variance: 0.03Mbps
  Min: 17.15Mbps
  Max: 17.72Mbps

Latency:
  Mean: 18.54Mbps
  Variance: 4.38Mbps
  Min: 15.73Mbps
  Max: 24.19Mbps

Packet Loss:
  Mean: 0.10%
  Variance: 0.08%
  Min: 0.00%
  Max: 1.00%
$ checkinternet display --yaml_file troubleshooting.yaml --format html > troubleshooting.html
```

![HTML Plot](docs/DiplayHTML.PNG)

## Automatic Checking

You can setup a cronjob to automatically run the troubleshooter at some interval. E.g., once every hour between midnight and 7AM:

```shell
crontab -e
```

```bash
0 0-7 * * * source /home/USER/git/internet-troubleshooter/my_env/bin/activate && checkinternet --debug run --yaml_file /home/USER/troubleshooting.yaml >> /home/USER/troubleshooting.log 2>&1
```
