"""
Minimal main script for presentation purposes.

Shows how the system fetches data from OpenWeather in a few lines.
"""
from openweather_data_provider import OpenWeatherDataProvider


def main():
    print('DÉMO: Surveillance qualité de l\'air via OpenWeather')
    provider = OpenWeatherDataProvider()
    reading = provider.fetch()

    print('Timestamp:', reading['timestamp'])
    print('Air quality (PPM):', reading['air_quality']['ppm'])
    print('Temperature (°C):', reading['temperature'])
    print('Humidity (%):', reading['humidity'])
    loc = reading.get('location') or {}
    print('Location:', loc.get('latitude'), loc.get('longitude'))


if __name__ == '__main__':
    main()
