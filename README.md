# MiniSEED Pipeline Converter

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![GitHub issues](https://img.shields.io/github/issues/mitrosoftlabs/mseed_pipeline_converter)](https://github.com/mitrosoftlabs/mseed_pipeline_converter/issues)

A robust pipeline for converting MiniSEED waveform data to CSS3.0 format with comprehensive support for FDSN web services, metadata processing, and response file generation.

## 🌟 Features

- **Multi-source Data Loading**: Support for both local MiniSEED files and FDSN web service data retrieval
- **Complete CSS3.0 Database Generation**: Creates all required CSS3.0 tables (network, site, affiliation, sitechan, instrument, sensor, wfdisc)
- **Automatic Response File Generation**: Creates response files in PAZFIR format according to CSS3.0 specifications
- **Metadata Integration**: Seamless integration with StationXML metadata and FDSN station services
- **Interactive & Command-Line Modes**: Both user-friendly interactive mode and powerful CLI interface
- **Archive Creation**: Optional ZIP archive generation for easy data distribution
- **Visualization Support**: Built-in waveform plotting capabilities
- **Robust Error Handling**: Comprehensive logging and error management

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/mitrosoftlabs/mseed_pipeline_converter.git
cd mseed_pipeline_converter
pip install -r requirements.txt
```

### Interactive Mode

```bash
python mseed_pipeline_converter.py
```

Follow the interactive prompts to configure your conversion.

### Command Line Examples

**Convert local MiniSEED file with StationXML metadata:**
```bash
python mseed_pipeline_converter.py -i data.mseed -x metadata.xml -o output_dir --archive
```

**Download data from FDSN and convert:**
```bash
python mseed_pipeline_converter.py --client IRIS -n IU -s ANMO -c BHZ \
  -st 2024-01-01T00:00:00 -et 2024-01-01T01:00:00 --plot --archive
```

**Use record length instead of end time:**
```bash
python mseed_pipeline_converter.py --client GEOFON -n KZ -s PDGK -c "B*" -l 3600
```

## 📋 Requirements

- Python 3.8+
- ObsPy >= 1.3.0
- SQLAlchemy >= 1.4.0
- NumPy >= 1.19.0
- PyTZ
- Pisces
- Matplotlib (for plotting)
- Requests (for FDSN)

## 🔧 Usage

### Command Line Arguments

```
usage: mseed_pipeline_converter.py [-h] [-i INPUT] [-x STATIONXML] 
                                   [--client CLIENT] [-u USERNAME] [-p PASSWORD]
                                   [--timeout TIMEOUT] [-n NET] [-s STA] [--loc LOC]
                                   [-c CHAN] [-st STARTTIME] [-l LENGTH] [-et ENDTIME]
                                   [-o OUTPUT] [--name NAME] [-w WAVEFORM_DIR]
                                   [-a] [--archive] [--plot] [--no-cleanup] [-v] [-q]

Enhanced MiniSEED to CSS3.0 Converter

Input Options:
  -i, --input           MiniSEED input file path
  -x, --stationxml      StationXML metadata file (optional for local files)

FDSN Options:
  --client              FDSN client (IRIS, GEOFON, EIDA, etc.)
  -u, --username        Username for FDSN authentication
  -p, --password        Password for FDSN authentication
  --timeout             FDSN request timeout in seconds (default: 120)

Data Selection:
  -n, --net             Network code (default: *)
  -s, --sta             Station code (default: *)
  --loc, --location     Location code (default: *)
  -c, --chan            Channel code (default: *)

Time Selection:
  -st, --starttime      Start time (YYYY-MM-DDTHH:MM:SS)
  -et, --endtime        End time (YYYY-MM-DDTHH:MM:SS)
  -l, --length          Record length in seconds

Output Options:
  -o, --output          Output directory (default: current directory)
  --name                CSS3.0 database name (default: auto-generated)
  -w, --waveform-dir    Separate directory for waveform files

Processing Options:
  -a, --absolute-paths  Use absolute paths in wfdisc.dir field
  --archive             Create ZIP archive of CSS3.0 database
  --plot                Generate waveform plots
  --no-cleanup          Disable ObsPy stream cleanup
  -v, --verbose         Enable verbose logging
  -q, --quiet           Suppress all output except errors
```

### Supported FDSN Clients

- IRIS, GEOFON, EIDA, EMSC, ETH, GFZ, INGV, IPGP, RESIF, USGS
- And many others (see full list with `--help`)

### Time Format Support

The converter supports multiple time formats:
- `YYYY-MM-DDTHH:MM:SS` (ISO format)
- `YYYY-MM-DD:HH:MM:SS`
- `YYYY-MM-DD` (time defaults to 00:00:00)
- `YYYYJJJTHH:MM:SS` (Julian day format)
- `YYYYJJJ` (Julian day only)

## 📁 Output Structure

The converter generates a complete CSS3.0 database structure:

```
output_directory/
├── database_name.network      # Network information
├── database_name.site         # Station locations
├── database_name.affiliation  # Network-station relationships
├── database_name.sitechan     # Channel configurations
├── database_name.instrument   # Instrument descriptions
├── database_name.sensor       # Sensor calibrations
├── database_name.wfdisc       # Waveform descriptors
├── database_name.w            # Binary waveform data
├── response/                  # Response files directory
│   ├── sensor1.net.sta.chan   # PAZFIR response files
│   └── sensor2.net.sta.chan
└── database_name.zip          # Optional archive
```

## 🔬 CSS3.0 Format Compliance

The converter generates fully compliant CSS3.0 format files:

- **Fixed-width ASCII tables** with proper field positioning
- **PAZFIR response files** following exact CSS3.0 specifications
- **Proper time handling** with epoch timestamps and Julian dates
- **Correct calibration calculations** for instrument responses
- **Complete metadata linkage** between all tables

## 🛠️ Advanced Features

### Custom Response File Generation

The converter automatically generates response files in PAZFIR format with:
- Poles and zeros from StationXML
- FIR filter coefficients
- Proper field positioning according to CSS3.0 specs
- Multiple response stages support

### Metadata Processing

- Automatic network/station/channel hierarchy creation
- Instrument response analysis and classification
- Calibration value calculations (nm/count)
- Temporal metadata handling

### Error Handling

- Comprehensive logging system
- Graceful handling of missing metadata
- Data validation and constraint checking
- Detailed error reporting

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

### Development Setup

```bash
git clone https://github.com/mitrosoftlabs/mseed_pipeline_converter.git
cd mseed_pipeline_converter
pip install -r requirements-dev.txt
```

### Running Tests

```bash
python -m pytest tests/
```

## 📄 License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License - see the [LICENSE](LICENSE) file for details.

### Commercial Use
This software is **not available for commercial use** without explicit written permission. For commercial licensing inquiries, please contact [mitrosoftlabs@gmail.com](mailto:mitrosoftlabs@gmail.com).

## 🙏 Acknowledgments

- Based on original work by D.Gordienko (KNDC)
- Built using [ObsPy](https://obspy.org/) seismological library
- CSS3.0 format specifications from NNSA Knowledge Base
- FDSN web services infrastructure

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/mitrosoftlabs/mseed_pipeline_converter/issues)
- **Documentation**: [Wiki](https://github.com/mitrosoftlabs/mseed_pipeline_converter/wiki)
- **Email**: [mitrosoftlabs@gmail.com](mailto:mitrosoftlabs@gmail.com)

## 🚀 Citation

If you use this software in your research, please cite:

```bibtex
@software{mseed_pipeline_converter,
  title = {MiniSEED Pipeline Converter},
  author = {MitroSoft Labs},
  year = {2024},
  url = {https://github.com/mitrosoftlabs/mseed_pipeline_converter},
  version = {2.1}
}
```