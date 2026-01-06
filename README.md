
# LoRa Modulation Jam

Programmatically send packets between two stations across a set of LoRa radio configurations.

Given nodes at two different locations with computers attached via USB, run one of these commands within a few minutes of each other on each computer:

`python modjam.py run --this-station=A` and `python modjam.py run --this-station=B`

Each station will iterate through the full permutation of LoRa radio settings.

Use the parameters to change the set of settings used:

This will run for all BWs, but only test SF 7 and 11, coding rate 5, and power level 1.
```
python3 ./modjam.py run --this-station=A --spread-factor=7 --spread-factor=11 --coding-rate=5 --power=1
```
