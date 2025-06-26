#!/usr/bin/env python3
# VSB
# Enhanced MiniSEED Pipeline Converter

"""
Enhanced MiniSEED Pipeline Converter
=====================================

A robust converter for transforming MiniSEED files to CSS3.0 format
with support for both FDSN web services and local file processing.

Features:
- Local MiniSEED file processing
- FDSN web service data retrieval
- StationXML metadata integration
- Automatic response file generation (PAZFIR format)
- Complete CSS3.0 database creation
- Interactive and command-line modes

Version: 2.1
Author: Enhanced version based on original by D.Gordienko (KNDC)
Email: mitrosoftlabs@gmail.com
License: Creative Commons Attribution-NonCommercial 4.0 International License
"""

import argparse
import logging
import os
import readline
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import operator
import re
import getpass
import sys

import numpy as np
import pytz
import sqlalchemy as sa
from obspy import Stream, UTCDateTime, read
from obspy.clients.fdsn import Client
from obspy.core.inventory import Inventory, read_inventory
import pisces.schema.css3 as css3

readline.set_completer_delims(" \t\n;")
readline.parse_and_bind("tab: complete")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mseed_pipeline_converter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ConversionConfig:
    """Configuration for MiniSEED to CSS3.0 conversion."""
    # Input/Output paths
    mseed_file: Optional[Path] = None
    stationxml_file: Optional[Path] = None
    output_dir: Path = Path.cwd()
    database_name: Optional[str] = None
    waveform_dir: Optional[Path] = None
    
    # FDSN parameters
    fdsn_client: str = "IRIS"
    username: Optional[str] = None
    password: Optional[str] = None
    timeout: float = 120.0
    
    # Data selection parameters
    network: str = "*"
    station: str = "*"
    location: str = "*"
    channel: str = "*"
    starttime: Optional[datetime] = None
    endtime: Optional[datetime] = None
    record_length: Optional[int] = None
    
    # Processing options
    use_absolute_paths: bool = False
    create_archive: bool = False
    show_plot: bool = False
    cleanup_data: bool = True


# Utility functions
def unixtime_now() -> float:
    """Get current Unix timestamp."""
    return float(datetime.now(timezone.utc).strftime("%s.%f")[:-3])


def safe_float(value) -> Optional[float]:
    """Safely parse float value."""
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def safe_int(value) -> Optional[int]:
    """Safely parse integer value."""
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def safe_str(value) -> str:
    """Safely parse string value."""
    try:
        result = str(value).strip() if value is not None else ""
        return result if result else "-"
    except (ValueError, TypeError):
        return "-"


def parse_juldate(dt: datetime) -> int:
    """Parse Julian date from datetime."""
    try:
        return int(f"{dt.year}{dt.timetuple().tm_yday:03d}")
    except (AttributeError, ValueError):
        return -1


def parse_timestamp(dt) -> float:
    """Parse timestamp from datetime-like object."""
    try:
        if hasattr(dt, 'timestamp'):
            return dt.timestamp
        elif hasattr(dt, 'datetime'):
            return dt.datetime.timestamp()
        else:
            return float(dt)
    except (AttributeError, ValueError):
        return 9999999999.999


def valid_timestamp(s: str) -> datetime:
    """Validate timestamp string and convert to datetime."""
    time_formats = [
        '%Y-%m-%d:%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S', 
        '%Y%jT%H:%M:%S',
        '%Y-%j:%H:%M:%S',
        '%Y-%jT%H:%M:%S',
        '%Y-%m-%d',
        '%Y%j',
        '%Y-%j'
    ]
    
    for fmt in time_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    
    raise argparse.ArgumentTypeError(f"Invalid timestamp format: {s}")


def get_user_input(prompt: str, default: str = "", required: bool = False) -> str:
    """Get user input with default value."""
    display_default = f" (default: {default})" if default else ""
    full_prompt = f"{prompt}{display_default}: "
    
    while True:
        try:
            user_input = input(full_prompt).strip()
            
            if user_input:
                return user_input
            elif default:
                return default
            elif not required:
                return ""
            else:
                print("❌ This field is required!")
                continue
                
        except KeyboardInterrupt:
            print("\n👋 Operation cancelled by user")
            sys.exit(0)
        except EOFError:
            print("\n❌ Input error")
            sys.exit(1)


def get_password(prompt: str = "Password") -> str:
    """Get password input (hidden)."""
    try:
        return getpass.getpass(f"{prompt}: ")
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user")
        sys.exit(0)
    except EOFError:
        print("\n❌ Password input error")
        sys.exit(1)


def get_datetime_input(prompt: str) -> datetime:
    """Get datetime input from user with format validation."""
    time_formats = [
        ('%Y-%m-%d:%H:%M:%S', 'YYYY-MM-DD:HH:MM:SS'),
        ('%Y-%m-%dT%H:%M:%S', 'YYYY-MM-DDTHH:MM:SS'), 
        ('%Y%jT%H:%M:%S', 'YYYYJJJTHH:MM:SS'),
        ('%Y-%j:%H:%M:%S', 'YYYY-JJJ:HH:MM:SS'),
        ('%Y-%m-%d', 'YYYY-MM-DD'),
        ('%Y%j', 'YYYYJJJ'),
        ('%Y-%j', 'YYYY-JJJ')
    ]
    
    print(f"\n{prompt}")
    print("Supported formats:")
    for fmt, example in time_formats:
        sample_time = datetime.now().strftime(fmt)
        print(f"  {example} (example: {sample_time})")
    
    while True:
        time_str = get_user_input("Enter time", required=True)
        
        for fmt, _ in time_formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        
        print("❌ Invalid time format! Please try again.")


class ResponseUnitsMapper:
    """Maps response units to CSS3.0 format."""
    
    UNIT_MAP = {
        "D": ["M"],
        "V": ["M/S", "M/SEC"],
        "A": ["M/S**2", "M/(S**2)", "M/SEC**2", "M/(SEC**2)", "M/S/S"]
    }
    
    @classmethod
    def get_response_type(cls, units: str, description: str = "") -> str:
        """Determine response type from units."""
        if not units:
            logger.warning(f"⚠️  No units provided for response: {description}")
            return ''
        
        units_upper = units.upper()
        for response_type, unit_list in cls.UNIT_MAP.items():
            if units_upper in unit_list:
                logger.info(f"✅ Response type: ({units}) → ({response_type}) - {description}")
                return response_type
        
        logger.warning(f"⚠️  Unknown units: ({units}) - {description}")
        return ''


# Enhanced CSS3.0 table definitions
class Network(css3.Base):
    __tablename__ = 'network'
    __table_args__ = (sa.PrimaryKeyConstraint('net'),)

    net = sa.Column(sa.String, info={'default': '-', 'dtype': 'a8', 'width': 8, 'format': '8.8s'})
    netname = sa.Column(sa.String, info={'default': '-', 'dtype': 'a80', 'width': 80, 'format': '80.80s'})
    nettype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a4', 'width': 4, 'format': '4.4s'})
    auth = sa.Column(sa.String, info={'default': '-', 'dtype': 'a15', 'width': 15, 'format': '15.15s'})
    commid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Site(css3.Base):
    __tablename__ = 'site'
    __table_args__ = (sa.PrimaryKeyConstraint('sta', 'ondate'),)
    
    sta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    ondate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    offdate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    lat = sa.Column(sa.Float, info={'default': -999.0, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    lon = sa.Column(sa.Float, info={'default': -999.0, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    elev = sa.Column(sa.Float, info={'default': -999.0, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    staname = sa.Column(sa.String, info={'default': '-', 'dtype': 'a50', 'width': 50, 'format': '50.50s'})
    statype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a4', 'width': 4, 'format': '4.4s'})
    refsta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    dnorth = sa.Column(sa.Float, info={'default': 0.0, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    deast = sa.Column(sa.Float, info={'default': 0.0, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Affiliation(css3.Base):
    __tablename__ = 'affiliation'
    __table_args__ = (sa.PrimaryKeyConstraint('net', 'sta'),)

    net = sa.Column(sa.String, info={'default': '-', 'dtype': 'a8', 'width': 8, 'format': '8.8s'})
    sta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Sitechan(css3.Base):
    __tablename__ = 'sitechan'
    __table_args__ = (sa.PrimaryKeyConstraint('chanid'),)
    
    sta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    chan = sa.Column(sa.String, info={'default': '-', 'dtype': 'a8', 'width': 8, 'format': '8.8s'})
    ondate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    chanid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    offdate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    ctype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a4', 'width': 4, 'format': '4.4s'})
    edepth = sa.Column(sa.Float, info={'default': -1, 'dtype': 'float', 'width': 9, 'format': '9.4f'})
    hang = sa.Column(sa.Float, info={'default': -1.0, 'dtype': 'float', 'width': 6, 'format': '6.1f'})
    vang = sa.Column(sa.Float, info={'default': -1.0, 'dtype': 'float', 'width': 6, 'format': '6.1f'})
    descrip = sa.Column(sa.String, info={'default': '-', 'dtype': 'a50', 'width': 50, 'format': '50.50s'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Instrument(css3.Base):
    __tablename__ = 'instrument'
    __table_args__ = (sa.PrimaryKeyConstraint('inid'),)
    
    inid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    insname = sa.Column(sa.String, info={'default': '-', 'dtype': 'a50', 'width': 50, 'format': '50.50s'})
    instype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    band = sa.Column(sa.String, info={'default': '-', 'dtype': 'a1', 'width': 1, 'format': '1.1s'})
    digital = sa.Column(sa.String, info={'default': '-', 'dtype': 'a1', 'width': 1, 'format': '1.1s'})
    samprate = sa.Column(sa.Float, info={'default': -1.0, 'dtype': 'float', 'width': 11, 'format': '11.7f'})
    ncalib = sa.Column(sa.Float, info={'default': 1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    ncalper = sa.Column(sa.Float, info={'default': 1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    dir = sa.Column(sa.String, info={'default': '-', 'dtype': 'a64', 'width': 64, 'format': '64.64s'})
    dfile = sa.Column(sa.String, info={'default': '-', 'dtype': 'a32', 'width': 32, 'format': '32.32s'})
    rsptype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Sensor(css3.Base):
    __tablename__ = 'sensor'
    __table_args__ = (sa.PrimaryKeyConstraint('sta', 'chan', 'time'),)

    sta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    chan = sa.Column(sa.String, info={'default': '-', 'dtype': 'a8', 'width': 8, 'format': '8.8s'})
    time = sa.Column(sa.Float(53), info={'default': 9999999999.999, 'dtype': 'float', 'width': 17, 'format': '17.5f'})
    endtime = sa.Column(sa.Float(53), info={'default': 9999999999.999, 'dtype': 'float', 'width': 17, 'format': '17.5f'})
    inid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    chanid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    jdate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    calratio = sa.Column(sa.Float, info={'default': -1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    calper = sa.Column(sa.Float, info={'default': 1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    tshift = sa.Column(sa.Float, info={'default': 0.0, 'dtype': 'float', 'width': 6, 'format': '6.2f'})
    instant = sa.Column(sa.String, info={'default': 'y', 'dtype': 'a1', 'width': 1, 'format': '1.1s'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class Wfdisc(css3.Base):
    __tablename__ = 'wfdisc'
    __table_args__ = (sa.PrimaryKeyConstraint('sta', 'chan', 'time'),)
    
    sta = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    chan = sa.Column(sa.String, info={'default': '-', 'dtype': 'a8', 'width': 8, 'format': '8.8s'})
    time = sa.Column(sa.Float(53), info={'default': -9999999999.999, 'dtype': 'float', 'width': 17, 'format': '17.5f'})
    wfid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    chanid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    jdate = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    endtime = sa.Column(sa.Float(53), info={'default': -9999999999.999, 'dtype': 'float', 'width': 17, 'format': '17.5f'})
    nsamp = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    samprate = sa.Column(sa.Float, info={'default': -1.0, 'dtype': 'float', 'width': 11, 'format': '11.7f'})
    calib = sa.Column(sa.Float, info={'default': 1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    calper = sa.Column(sa.Float, info={'default': 1.0, 'dtype': 'float', 'width': 16, 'format': '16.6f'})
    instype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a6', 'width': 6, 'format': '6.6s'})
    segtype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a1', 'width': 1, 'format': '1.1s'})
    datatype = sa.Column(sa.String, info={'default': '-', 'dtype': 'a2', 'width': 2, 'format': '2.2s'})
    clip = sa.Column(sa.String, info={'default': '-', 'dtype': 'a1', 'width': 1, 'format': '1.1s'})
    dir = sa.Column(sa.String, info={'default': '-', 'dtype': 'a64', 'width': 64, 'format': '64.64s'})
    dfile = sa.Column(sa.String, info={'default': '-', 'dtype': 'a32', 'width': 32, 'format': '32.32s'})
    foff = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 10, 'format': '10d'})
    commid = sa.Column(sa.Integer, info={'default': -1, 'dtype': 'int', 'width': 8, 'format': '8d'})
    lddate = sa.Column(sa.Float(53), info={'default': unixtime_now(), 'dtype': 'float', 'width': 17, 'format': '17.5f'})


class CSS3Converter:
    """Main converter class for MiniSEED to CSS3.0 format."""
    
    def __init__(self, config: ConversionConfig):
        self.config = config
        self._setup_database()
        self._setup_counters()
        self.waveform_file = None
        self.file_offset = 0
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()
    
    def _setup_database(self):
        """Setup SQLite database and tables."""
        self.engine = sa.create_engine("sqlite://")
        self.session = sa.orm.Session(self.engine)
        
        # Create all tables
        tables = [Network, Site, Affiliation, Sitechan, Instrument, Sensor, Wfdisc]
        for table in tables:
            table.__table__.create(self.engine, checkfirst=True)
    
    def _setup_counters(self):
        """Initialize ID counters."""
        self.counters = {"wfid": 1, "chanid": 1, "inid": 1}
    
    def _get_next_id(self, counter_name: str) -> int:
        """Get next available ID."""
        current_id = self.counters[counter_name]
        self.counters[counter_name] += 1
        return current_id
    
    def _add_record(self, record) -> bool:
        """Add record to database with error handling."""
        try:
            self.session.add(record)
            self.session.commit()
            return True
        except Exception:
            logger.debug(f"Record exists or constraint violation: {type(record).__name__}")
            self.session.rollback()
            return False
    
    def _cleanup(self):
        """Clean up resources."""
        if self.waveform_file:
            self.waveform_file.close()
        if self.session:
            self.session.close()
    
    def load_stream(self) -> Stream:
        """Load stream from file or FDSN."""
        if self.config.mseed_file:
            return self._load_from_file()
        else:
            return self._load_from_fdsn()
    
    def _load_from_file(self) -> Stream:
        """Load stream from MiniSEED file."""
        try:
            logger.info(f"📂 Loading: {self.config.mseed_file}")
            stream = read(str(self.config.mseed_file))
            
            if self.config.cleanup_data:
                stream._cleanup()
            stream.sort()
            
            logger.info(f"✅ Loaded {len(stream)} traces")
            return stream
            
        except Exception as e:
            logger.error(f"❌ Failed to load {self.config.mseed_file}: {e}")
            return Stream()
    
    def _load_from_fdsn(self) -> Stream:
        """Load stream from FDSN web services."""
        try:
            logger.info(f"🌐 Connecting to {self.config.fdsn_client}")
            
            client = Client(
                self.config.fdsn_client,
                user=self.config.username,
                password=self.config.password,
                timeout=self.config.timeout
            )
            
            # Handle time configuration
            if self.config.record_length and not self.config.starttime and not self.config.endtime:
                endtime = datetime.now(tz=pytz.UTC)
                starttime = endtime - timedelta(seconds=self.config.record_length)
            elif self.config.starttime and self.config.record_length and not self.config.endtime:
                starttime = self.config.starttime
                endtime = starttime + timedelta(seconds=self.config.record_length)
            else:
                starttime = self.config.starttime or (datetime.now(tz=pytz.UTC) - timedelta(hours=1))
                endtime = self.config.endtime or datetime.now(tz=pytz.UTC)
            
            if starttime >= endtime:
                raise ValueError(f"End time ({endtime}) must be after start time ({starttime})")
            
            logger.info(f"📊 Requesting: {self.config.network}.{self.config.station}.{self.config.location}.{self.config.channel}")
            logger.info(f"📅 Time range: {starttime} → {endtime}")
            
            stream = client.get_waveforms(
                network=self.config.network,
                station=self.config.station,
                location=self.config.location,
                channel=self.config.channel,
                starttime=UTCDateTime(starttime),
                endtime=UTCDateTime(endtime),
                attach_response=False
            )
            
            if self.config.cleanup_data:
                stream._cleanup()
            stream.sort()
            
            logger.info(f"✅ Retrieved {len(stream)} traces")
            return stream
            
        except Exception as e:
            logger.error(f"❌ FDSN request failed: {e}")
            return Stream()
    
    def get_inventory(self, trace) -> Optional[Inventory]:
        """Get inventory for trace from StationXML or FDSN."""
        # Try StationXML file first
        if self.config.stationxml_file:
            try:
                inventory = read_inventory(str(self.config.stationxml_file))
                
                # Filter for this trace
                filtered = inventory.select(
                    network=trace.stats.network,
                    station=trace.stats.station,
                    channel=trace.stats.channel,
                    location=trace.stats.location,
                    starttime=trace.stats.starttime,
                    endtime=trace.stats.endtime
                )
                
                if filtered:
                    logger.debug(f"📋 Using StationXML metadata for {trace.id}")
                    return filtered
                    
            except Exception as e:
                logger.warning(f"⚠️  StationXML error for {trace.id}: {e}")
        
        # Fallback to FDSN
        try:
            logger.debug(f"🌐 Getting FDSN metadata for {trace.id}")
            
            client = Client(
                self.config.fdsn_client,
                user=self.config.username,
                password=self.config.password,
                timeout=self.config.timeout
            )
            
            inventory = client.get_stations(
                network=trace.stats.network,
                station=trace.stats.station,
                location=trace.stats.location,
                channel=trace.stats.channel,
                starttime=trace.stats.starttime,
                endtime=trace.stats.endtime,
                level='response'
            )
            
            return inventory
            
        except Exception as e:
            logger.error(f"❌ Failed to get metadata for {trace.id}: {e}")
            return None
    
    def create_response_file(self, response_path: Path, inventory: Inventory, 
                           network, station, channel) -> None:
        """
        Create response file in correct PAZFIR format according to CSS3.0 specification.
        
        This implementation follows the exact format from CSS_description.txt:
        - Exact field positioning (1-12, 14-15, 17-28, 30-35, 37-80)
        - 4 values per pole/zero (real, imag, real_error, imag_error)
        - Right-justified counters in positions 1-8
        - f12.4 format for FIR sample rates
        """
        try:
            response = channel.response
            sensitivity = response.instrument_sensitivity
            
            if not response or not sensitivity:
                raise ValueError(f"No response/sensitivity for {channel.code}")
            
            # Determine response units correctly
            response_units = ResponseUnitsMapper.get_response_type(
                sensitivity.input_units, sensitivity.input_units_description
            )
            
            # Collect response stages
            paz_stages = []
            fir_stages = []
            
            for stage in response.response_stages:
                stage_name = stage.__class__.__name__
                
                if stage_name == 'PolesZerosResponseStage' and hasattr(stage, 'pz_transfer_function_type'):
                    paz_stages.append({
                        'sequence': stage.stage_sequence_number,
                        'transfer_type': stage.pz_transfer_function_type,
                        'input_units': stage.input_units,
                        'output_units': stage.output_units,
                        'norm_factor': stage.normalization_factor,
                        'norm_freq': stage.normalization_frequency,
                        'poles': stage.poles,
                        'zeros': stage.zeros,
                    })
                
                elif stage_name == 'CoefficientsTypeResponseStage' and hasattr(stage, 'cf_transfer_function_type'):
                    fir_stages.append({
                        'sequence': stage.stage_sequence_number,
                        'transfer_type': stage.cf_transfer_function_type,
                        'input_units': stage.input_units,
                        'output_units': stage.output_units,
                        'input_rate': stage.decimation_input_sample_rate,
                        'decimation': stage.decimation_factor,
                        'numerators': stage.numerator,
                        'denominators': stage.denominator,
                    })
            
            # Generate response content following exact CSS3.0 format
            response_lines = []
            
            # Header comments (Lines 1-L)
            response_lines.extend([
                "# Response file generated by Enhanced CSS3.0 Converter",
                f"# Source: {inventory.sender or 'Unknown'} ({inventory.source or 'Unknown'})",
                f"# Module: {inventory.module or 'ObsPy'}",
                f"# Created: {inventory.created or datetime.now().isoformat()}",
                "# Response type: pazfir",
                "# Contact: Enhanced CSS3.0 Converter",
                "#",
                f"# Station/Channel/Location: {station.code}/{channel.code}/{channel.location_code or ''}",
                f"# Channel description: {channel.description or 'Unknown'}",
                f"# Sensor description: {channel.sensor.description if channel.sensor else 'Unknown'}",
                f"# Channel active period: {channel.start_date} - {channel.end_date or 'ongoing'}",
                "#",
                f"# Instrument sensitivity: {sensitivity.value:.10e}",
                f"# Sensitivity frequency: {sensitivity.frequency:.10e}",
                f"# Input units: {sensitivity.input_units} - {sensitivity.input_units_description}",
                f"# Output units: {sensitivity.output_units} - {sensitivity.output_units_description}",
                f"# Response units: {response_units}",
                "#"
            ])
            
            # Instrument type/description line (Line L+1)
            instrument_desc = channel.sensor.description if channel.sensor else "Unknown Sensor"
            response_lines.append(f"# {instrument_desc[:78]}")
            
            # Sort stages by sequence number
            all_stages = []
            for stage in paz_stages:
                all_stages.append(('paz', stage))
            for stage in fir_stages:
                all_stages.append(('fir', stage))
            
            all_stages.sort(key=lambda x: x[1]['sequence'])
            
            # Process each stage according to CSS3.0 specification
            for stage_type, stage_data in all_stages:
                
                if stage_type == 'paz':
                    # PAZ section header line - EXACT format from specification
                    # Positions: 1-12, 14-15, 17-28, 30-35, 37-80
                    source_str = inventory.source or "unknown"
                    response_lines.append(
                        f"{'theoretical':<12}  "    # Position 1-12: response source
                        f"{stage_data['sequence']:2d} "    # Position 14-15: sequence number  
                        f"{'unknown':<12}  "        # Position 17-28: description
                        f"{'paz':<6}  "             # Position 30-35: response type
                        f"{source_str:>44}"         # Position 37-80: author/source
                    )
                    
                    # Normalization factor line (2 floats: A0 and frequency)
                    response_lines.append(
                        f"{stage_data['norm_factor']:.10e}  {stage_data['norm_freq']:.10e}"
                    )
                    
                    # Number of poles (position 1-8, i8 format, right-justified)
                    response_lines.append(f"{len(stage_data['poles']):>8d}")
                    
                    # Poles data (4 fields: real, imag, real_error, imag_error)
                    for pole in stage_data['poles']:
                        response_lines.append(
                            f"{pole.real:.10e} {pole.imag:.10e} {0.0:.10e} {0.0:.10e}"
                        )
                    
                    # Number of zeros (position 1-8, i8 format, right-justified)
                    response_lines.append(f"{len(stage_data['zeros']):>8d}")
                    
                    # Zeros data (4 fields: real, imag, real_error, imag_error)
                    for zero in stage_data['zeros']:
                        response_lines.append(
                            f"{zero.real:.10e} {zero.imag:.10e} {0.0:.10e} {0.0:.10e}"
                        )
                
                elif stage_type == 'fir':
                    # FIR section header line - EXACT format from specification
                    source_str = inventory.source or "unknown"
                    response_lines.append(
                        f"{'theoretical':<12}  "    # Position 1-12: response source
                        f"{stage_data['sequence']:2d} "    # Position 14-15: sequence number
                        f"{'unknown':<12}  "        # Position 17-28: description
                        f"{'fir':<6}  "             # Position 30-35: response type
                        f"{source_str:>44}"         # Position 37-80: author/source
                    )
                    
                    # Input sample rate (f12.4 format) and decimation factor
                    response_lines.append(
                        f"{stage_data['input_rate']:12.4f}  {stage_data['decimation']:d}"
                    )
                    
                    # Number of numerator coefficients (position 1-8, i8 format, right-justified)
                    response_lines.append(f"{len(stage_data['numerators']):>8d}")
                    
                    # Numerator coefficients (2 fields: real, imag)
                    for num in stage_data['numerators']:
                        response_lines.append(f"{num.real:.10e} {num.imag:.10e}")
                    
                    # Number of denominator coefficients (position 1-8, i8 format, right-justified)
                    response_lines.append(f"{len(stage_data['denominators']):>8d}")
                    
                    # Denominator coefficients (2 fields: real, imag)
                    for den in stage_data['denominators']:
                        response_lines.append(f"{den.real:.10e} {den.imag:.10e}")
            
            # Write file with Unix line endings
            with open(response_path, 'w', newline='\n') as f:
                for line in response_lines:
                    f.write(line + '\n')
            
            logger.debug(f"📄 Created response: {response_path.name}")
            
        except Exception as e:
            logger.error(f"❌ Response file creation failed: {e}")
            raise
    
    def setup_output_directories(self) -> Tuple[Path, Path, Path]:
        """Setup and create output directories."""
        # Main output directory
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Waveform directory
        wf_dir = self.config.waveform_dir or self.config.output_dir
        wf_dir.mkdir(parents=True, exist_ok=True)
        
        # Response directory
        resp_dir = self.config.output_dir / 'response'
        resp_dir.mkdir(parents=True, exist_ok=True)
        
        return self.config.output_dir, wf_dir, resp_dir
    
    def open_waveform_file(self, waveform_path: Path):
        """Open waveform file for writing."""
        self.waveform_file = open(waveform_path, "wb")
        self.file_offset = 0
        logger.info(f"📝 Waveform file: {waveform_path.name}")
    
    def write_waveform_data(self, trace) -> int:
        """Write trace data and return file offset."""
        if not self.waveform_file:
            raise RuntimeError("Waveform file not opened")
        
        current_offset = self.file_offset
        trace.data.tofile(self.waveform_file)
        self.file_offset += trace.stats.npts * 4  # 4 bytes per int32
        return current_offset
    
    def process_trace(self, trace, inventory: Inventory) -> bool:
        """Process a single trace and create all database records."""
        try:
            network = inventory[0]
            station = network[0]
            channel = station[0]
            response = channel.response
            
            if not response or not response.instrument_sensitivity:
                logger.warning(f"⚠️  No response for {trace.id}")
                return False
            
            sensitivity = response.instrument_sensitivity
            response_units = ResponseUnitsMapper.get_response_type(
                sensitivity.input_units, sensitivity.input_units_description
            )
            
            # Calculate calibration values
            calib_value = 1.0
            calper_value = 1.0
            if sensitivity.value:
                calib_value = round((1.0 / sensitivity.value) * 1e9, 6)
            if sensitivity.frequency:
                calper_value = round(1.0 / sensitivity.frequency, 6)
            
            # Create all database records
            success = True
            
            # Network record
            network_record = Network(
                net=network.code,
                netname=safe_str(network.description)
            )
            self._add_record(network_record)
            
            # Site record
            site_record = Site(
                sta=station.code,
                ondate=parse_juldate(station.start_date) if station.start_date else -1,
                offdate=parse_juldate(station.end_date) if station.end_date else -1,
                lat=safe_float(station.latitude) or -999.0,
                lon=safe_float(station.longitude) or -999.0,
                elev=safe_float(station.elevation) or -999.0,
                staname=safe_str(station.site.name if station.site else station.code),
                statype=safe_str(station.vault) if hasattr(station, 'vault') else "-"
            )
            self._add_record(site_record)
            
            # Affiliation record
            affiliation_record = Affiliation(
                net=network.code,
                sta=station.code
            )
            self._add_record(affiliation_record)
            
            # Sitechan record
            chanid = self._get_next_id('chanid')
            sitechan_record = Sitechan(
                sta=station.code,
                chan=channel.code,
                chanid=chanid,
                ondate=parse_juldate(channel.start_date) if channel.start_date else -1,
                offdate=parse_juldate(channel.end_date) if channel.end_date else -1,
                edepth=safe_float(channel.depth) / 1000.0 if channel.depth else 0.0,
                hang=safe_float(channel.azimuth) or -1.0,
                vang=safe_float(channel.dip + 90.0) if channel.dip is not None else -1.0,
                descrip=safe_str(channel.description)
            )
            if not self._add_record(sitechan_record):
                success = False
            
            # Instrument record  
            inid = self._get_next_id('inid')
            sensor_desc = channel.sensor.description if channel.sensor else "unknown"
            instrument_dfile = f"{''.join(c for c in sensor_desc if c.isalnum()).lower()[:20]}.{network.code}.{station.code}.{channel.code}"
            
            instrument_record = Instrument(
                inid=inid,
                insname=safe_str(sensor_desc),
                samprate=safe_float(channel.sample_rate) or -1.0,
                ncalib=calib_value,
                ncalper=calper_value,
                dfile=instrument_dfile,
                dir='response',
                rsptype=response_units
            )
            if not self._add_record(instrument_record):
                success = False
            
            # Sensor record
            sensor_record = Sensor(
                sta=station.code,
                chan=channel.code,
                time=parse_timestamp(channel.start_date) if channel.start_date else 9999999999.999,
                endtime=parse_timestamp(channel.end_date) if channel.end_date else 9999999999.999,
                inid=inid,
                chanid=chanid,
                jdate=parse_juldate(channel.start_date) if channel.start_date else -1,
                calratio=1.0,
                calper=calper_value
            )
            self._add_record(sensor_record)
            
            # Write waveform data
            waveform_offset = self.write_waveform_data(trace)
            
            # Set waveform directory path
            if self.config.use_absolute_paths:
                wform_dir = str(self.config.waveform_dir or self.config.output_dir)
            else:
                wf_dir = self.config.waveform_dir or self.config.output_dir
                wform_dir = str(wf_dir.relative_to(self.config.output_dir))
            
            # Wfdisc record
            wfid = self._get_next_id('wfid')
            wfdisc_record = Wfdisc(
                sta=trace.stats.station,
                chan=trace.stats.channel,
                time=trace.stats.starttime.timestamp,
                wfid=wfid,
                chanid=chanid,
                jdate=parse_juldate(trace.stats.starttime.datetime),
                endtime=trace.stats.endtime.timestamp,
                nsamp=trace.stats.npts,
                samprate=trace.stats.sampling_rate,
                calib=calib_value,
                calper=calper_value,
                instype='-',
                datatype='i4',
                dir=wform_dir,
                foff=waveform_offset,
                dfile=f"{self.config.database_name}.w",
                segtype=response_units
            )
            self._add_record(wfdisc_record)
            
            # Create response file
            response_filename = instrument_dfile
            response_path = self.config.output_dir / 'response' / response_filename
            self.create_response_file(response_path, inventory, network, station, channel)
            
            logger.info(f"✅ Processed: {trace.id}")
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed processing {trace.id}: {e}")
            return False
    
    def write_css3_tables(self):
        """Write all CSS3.0 table files."""
        tables = [Network, Site, Affiliation, Sitechan, Instrument, Sensor, Wfdisc]
        
        for table in tables:
            filename = self.config.output_dir / f"{self.config.database_name}.{table.__tablename__}"
            logger.info(f"📄 Writing: {filename.name}")
            
            with open(filename, 'w') as f:
                for row in self.session.query(table):
                    f.write(str(row) + '\n')
    
    def create_archive(self):
        """Create ZIP archive of CSS3.0 database."""
        archive_path = self.config.output_dir / f"{self.config.database_name}.zip"
        
        logger.info(f"📦 Creating archive: {archive_path.name}")
        
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add waveform file
            wf_file = self.config.output_dir / f"{self.config.database_name}.w"
            if wf_file.exists():
                zf.write(wf_file, f"{self.config.database_name}/{self.config.database_name}.w")
            
            # Add CSS3.0 table files
            for table_name in ['network', 'site', 'affiliation', 'sitechan', 'instrument', 'sensor', 'wfdisc']:
                table_file = self.config.output_dir / f"{self.config.database_name}.{table_name}"
                if table_file.exists():
                    zf.write(table_file, f"{self.config.database_name}/{self.config.database_name}.{table_name}")
            
            # Add response files
            response_dir = self.config.output_dir / 'response'
            if response_dir.exists():
                for response_file in response_dir.glob('*'):
                    if response_file.is_file():
                        zf.write(response_file, f"{self.config.database_name}/response/{response_file.name}")
        
        logger.info(f"✅ Archive created: {archive_path}")
    
    def convert(self) -> bool:
        """Main conversion method."""
        try:
            logger.info("🚀 Starting MiniSEED to CSS3.0 conversion")
            
            # Load stream
            stream = self.load_stream()
            if not stream:
                logger.error("❌ No data to process")
                return False
            
            # Setup output directories
            self.setup_output_directories()
            
            # Set database name if not provided
            if not self.config.database_name:
                self.config.database_name = UTCDateTime(
                    stream[0].stats.starttime
                ).strftime("%Y%m%d%H%M%S")
            
            # Open waveform file
            waveform_filename = f"{self.config.database_name}.w"
            waveform_path = (self.config.waveform_dir or self.config.output_dir) / waveform_filename
            self.open_waveform_file(waveform_path)
            
            # Process each trace
            successful_traces = 0
            total_traces = len(stream)
            
            logger.info(f"📊 Processing {total_traces} traces")
            
            for i, trace in enumerate(stream, 1):
                logger.info(f"📈 Trace {i}/{total_traces}: {trace.id}")
                
                # Get inventory for this trace
                inventory = self.get_inventory(trace)
                if not inventory:
                    logger.error(f"❌ No metadata for {trace.id}")
                    continue
                
                # Process the trace
                if self.process_trace(trace, inventory):
                    successful_traces += 1
                else:
                    logger.warning(f"⚠️  Partial failure for {trace.id}")
            
            # Write CSS3.0 table files
            logger.info("📚 Writing CSS3.0 tables")
            self.write_css3_tables()
            
            # Create archive if requested
            if self.config.create_archive:
                self.create_archive()
            
            # Show plots if requested
            if self.config.show_plot:
                try:
                    self._show_plots(stream)
                except ImportError:
                    logger.warning("⚠️  Matplotlib not available for plotting")
                except Exception as e:
                    logger.warning(f"⚠️  Plot generation failed: {e}")
            
            # Summary
            logger.info(f"🎉 Conversion completed!")
            logger.info(f"📊 Success: {successful_traces}/{total_traces} traces")
            logger.info(f"📁 Output: {self.config.output_dir}")
            
            return successful_traces > 0
            
        except Exception as e:
            logger.error(f"❌ Conversion failed: {e}")
            return False
    
    def _show_plots(self, stream: Stream):
        """Generate and show plots for stream data."""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            
            plots_dir = self.config.output_dir / 'plots'
            plots_dir.mkdir(exist_ok=True)
            
            plot_file = os.path.join(plots_dir, f"{self.config.database_name}.png")
            stream.plot(outfile=plot_file)
            logger.info(f"📊 Plot saved: {plot_file}")                
        except ImportError:
            logger.warning("⚠️  Matplotlib not available for plotting")
        except Exception as e:
            logger.error(f"❌ Plot generation failed: {e}")


def interactive_mode() -> ConversionConfig:
    """Interactive configuration mode with user dialog."""
    print("🎯 Enhanced MiniSEED to CSS3.0 Converter")
    print("=" * 50)
    print("Welcome to interactive mode!")
    print()
    
    config = ConversionConfig()
    
    # Mode selection
    print("📋 Select operation mode:")
    print("1. Convert local MiniSEED file")
    print("2. Download data from FDSN")
    print()
    
    while True:
        mode = get_user_input("Select mode (1 or 2)", "1")
        if mode in ["1", "2"]:
            break
        print("❌ Please select 1 or 2")
    
    if mode == "1":
        # Local file mode
        print("\n📂 Local file mode")
        print("-" * 30)
        
        # Get MiniSEED file
        while True:
            mseed_path = get_user_input("Path to MiniSEED file", required=True)
            mseed_file = Path(mseed_path)
            if mseed_file.exists():
                config.mseed_file = mseed_file
                print(f"✅ File found: {mseed_file}")
                break
            else:
                print(f"❌ File not found: {mseed_file}")
        
        # Optional StationXML file
        print("\n📋 Metadata (optional)")
        xml_path = get_user_input("Path to StationXML file (Enter to skip)")
        if xml_path:
            xml_file = Path(xml_path)
            if xml_file.exists():
                config.stationxml_file = xml_file
                print(f"✅ StationXML file: {xml_file}")
            else:
                print(f"⚠️  StationXML file not found, will use FDSN metadata")
        
        # FDSN client for metadata fallback
        print(f"\n🌐 Select FDSN service for metadata (if StationXML not provided)")
        available_clients = ['IRIS', 'GEOFON', 'EIDA', 'EMSC', 'ETH', 'GFZ', 'INGV', 'IPGP', 'RESIF', 'USGS']
        print("Available services:", ", ".join(available_clients))
        
        while True:
            fdsn_client = get_user_input("FDSN service", "IRIS")
            if fdsn_client.upper() in [c.upper() for c in available_clients]:
                config.fdsn_client = fdsn_client.upper()
                break
            print("❌ Unknown FDSN service")
        
    else:
        # FDSN download mode
        print("\n🌐 FDSN download mode")
        print("-" * 30)
        
        # FDSN client selection
        available_clients = ['IRIS', 'GEOFON', 'EIDA', 'EMSC', 'ETH', 'GFZ', 'INGV', 'IPGP', 'RESIF', 'USGS']
        print("Available FDSN services:", ", ".join(available_clients))
        
        while True:
            fdsn_client = get_user_input("FDSN service", "IRIS")
            if fdsn_client.upper() in [c.upper() for c in available_clients]:
                config.fdsn_client = fdsn_client.upper()
                break
            print("❌ Unknown FDSN service")
        
        # Authentication (optional)
        print(f"\n🔐 Authentication for {config.fdsn_client} (optional)")
        username = get_user_input("Username (Enter to skip)")
        if username:
            config.username = username
            config.password = get_password("Password")
            print("✅ Authentication data saved")
        
        # Data selection parameters
        print(f"\n📊 Data selection parameters")
        print("Use * to select all available options")
        
        config.network = get_user_input("Network code", "*")
        config.station = get_user_input("Station code", "*") 
        config.location = get_user_input("Location code", "*")
        config.channel = get_user_input("Channel code", "*")
        
        # Time range
        print(f"\n📅 Time range")
        print("1. Last hour")
        print("2. Specify time manually")
        print("3. Specify record length")
        
        time_choice = get_user_input("Select option (1, 2 or 3)", "1")
        
        if time_choice == "1":
            config.endtime = datetime.now(tz=pytz.UTC)
            config.starttime = config.endtime - timedelta(hours=1)
            print(f"✅ Time: {config.starttime} → {config.endtime}")
        elif time_choice == "2":
            config.starttime = get_datetime_input("📅 Start time")
            config.endtime = get_datetime_input("📅 End time")
            
            if config.starttime >= config.endtime:
                print("❌ End time must be after start time!")
                config.endtime = config.starttime + timedelta(hours=1)
                print(f"✅ Automatically set: {config.starttime} → {config.endtime}")
        else:
            # Record length mode
            length_str = get_user_input("Record length in seconds", "3600")
            try:
                config.record_length = int(length_str)
                config.endtime = datetime.now(tz=pytz.UTC)
                config.starttime = config.endtime - timedelta(seconds=config.record_length)
                print(f"✅ Record length: {config.record_length} sec ({config.starttime} → {config.endtime})")
            except ValueError:
                print("❌ Invalid record length, using 1 hour")
                config.record_length = 3600
                config.endtime = datetime.now(tz=pytz.UTC)
                config.starttime = config.endtime - timedelta(seconds=3600)
    
    # Output settings
    print(f"\n📁 Output settings")
    output_path = get_user_input("Output directory", str(Path.cwd()))
    config.output_dir = Path(output_path)
    
    db_name = get_user_input("Database name (Enter for auto-generation)")
    if db_name:
        config.database_name = db_name
    
    # Optional separate waveform directory
    wf_path = get_user_input("Specify a waveform directory (Enter for same)")
    if wf_path:
        config.waveform_dir = Path(wf_path)
    
    # Processing options
    print(f"\n⚙️  Additional options")
    
    if get_user_input("Create ZIP archive? (y/n)", "n").lower().startswith('y'):
        config.create_archive = True
    
    if get_user_input("Generate plots? (y/n)", "n").lower().startswith('y'):
        config.show_plot = True
    
    if get_user_input("Use absolute paths? (y/n)", "n").lower().startswith('y'):
        config.use_absolute_paths = True
    
    if get_user_input("Disable data cleanup? (y/n)", "n").lower().startswith('y'):
        config.cleanup_data = False
    
    # Timeout settings
    timeout_str = get_user_input("FDSN request timeout (seconds)", "120")
    try:
        config.timeout = float(timeout_str)
    except ValueError:
        config.timeout = 120.0
        print("⚠️  Using default timeout: 120 seconds")
    
    # Summary
    print(f"\n📋 Configuration summary:")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    if config.mseed_file:
        print(f"📂 Mode: Local file")
        print(f"📄 MiniSEED: {config.mseed_file}")
        if config.stationxml_file:
            print(f"📋 StationXML: {config.stationxml_file}")
        else:
            print(f"🌐 Metadata: FDSN ({config.fdsn_client})")
    else:
        print(f"🌐 Mode: FDSN download")
        print(f"🌐 Service: {config.fdsn_client}")
        if config.username:
            print(f"👤 User: {config.username}")
        print(f"📊 Data: {config.network}.{config.station}.{config.location}.{config.channel}")
        if config.record_length:
            print(f"📅 Record length: {config.record_length} sec")
        else:
            print(f"📅 Time: {config.starttime} → {config.endtime}")
    
    print(f"📁 Output: {config.output_dir}")
    if config.waveform_dir:
        print(f"🌊 Waveform files: {config.waveform_dir}")
    if config.database_name:
        print(f"💾 Database: {config.database_name}")
    if config.create_archive:
        print(f"📦 Archive: Yes")
    if config.show_plot:
        print(f"📊 Plots: Yes")
    if config.use_absolute_paths:
        print(f"📍 Absolute paths: Yes")
    if not config.cleanup_data:
        print(f"🧹 Data cleanup: Disabled")
    
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Confirmation
    if not get_user_input("\nProceed with conversion? (y/n)", "y").lower().startswith('y'):
        print("👋 Operation cancelled")
        sys.exit(0)
    
    return config


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="""
        Enhanced MiniSEED to CSS3.0 Converter
        
        Convert MiniSEED waveform data to CSS3.0 format with support for:
        • Local MiniSEED file processing
        • FDSN web service data retrieval  
        • StationXML metadata integration
        • Automatic response file generation
        
        Examples:
          # Interactive mode
          python mseed_pipeline_converter.py
          
          # Convert local file with StationXML
          python mseed_pipeline_converter.py -i data.mseed -x metadata.xml -o output
          
          # Convert local file, get metadata from FDSN
          python mseed_pipeline_converter.py -i data.mseed -o output --client IRIS
          
          # Download from FDSN
          python mseed_pipeline_converter.py --client IRIS -n IU -s ANMO -c BHZ -st 2024-01-01T00:00:00 -et 2024-01-01T01:00:00
          
          # Use record length instead of end time
          python mseed_pipeline_converter.py --client IRIS -n KZ -s PDGK -c "B*" -l 3600 --archive
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "-i", "--input", "--mseed-file",
        type=Path,
        help="MiniSEED input file path"
    )
    
    # StationXML metadata file
    parser.add_argument(
        "-x", "--stationxml", "--xml",
        type=Path,
        help="StationXML metadata file (optional for local files)"
    )
    
    # FDSN client options
    parser.add_argument(
        "--client", "--fdsn-client",
        choices=['AUSPASS', 'BGR', 'EIDA', 'EMSC', 'ETH', 'GEOFON', 'GEONET', 'GFZ', 
                'ICGC', 'IESDMC', 'INGV', 'IPGP', 'IRIS', 'IRISPH5', 'ISC', 'KNMI', 
                'KOERI', 'LMU', 'NCEDC', 'NIEP', 'NOA', 'ODC', 'ORFEUS', 'RASPISHAKE', 
                'RESIF', 'RESIFPH5', 'SCEDC', 'TEXNET', 'UIB-NORSAR', 'USGS', 'USP'],
        default="IRIS",
        help="FDSN client for data/metadata retrieval (default: IRIS)"
    )
    
    parser.add_argument(
        "-u", "--user", "--username",
        help="Username for FDSN authentication"
    )
    
    parser.add_argument(
        "-p",  "--password",
        help="Password for FDSN authentication"
    )
    
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="FDSN request timeout in seconds (default: 120)"
    )
    
    # Data selection parameters
    parser.add_argument(
        "-n", "--net", "--network",
        default="*",
        help="Network code (default: *)"
    )
    
    parser.add_argument(
        "-s", "--sta", "--station",
        default="*",
        help="Station code (default: *)"
    )
    
    parser.add_argument(
        "--loc", "--location",
        default="*",
        help="Location code (default: *)"
    )
    
    parser.add_argument(
        "-c", "--chan", "--channel",
        default="*",
        help="Channel code (default: *)"
    )
    
    # Time selection (mutually exclusive)
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        "-st", "--starttime",
        type=valid_timestamp,
        help="Start time (YYYY-MM-DDTHH:MM:SS or other supported formats)"
    )
    
    time_group.add_argument(
        "-l", "--length", "--record-length",
        type=int,
        help="Record length in seconds from current time or starttime"
    )
    
    parser.add_argument(
        "-et", "--endtime",
        type=valid_timestamp,
        help="End time (YYYY-MM-DDTHH:MM:SS or other supported formats)"
    )
    
    # Output options
    parser.add_argument(
        "-o", "--output", "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Output directory for CSS3.0 files (default: current directory)"
    )
    
    parser.add_argument(
        "--name", "--database-name",
        help="CSS3.0 database name (default: auto-generated from timestamp)"
    )
    
    parser.add_argument(
        "-w", "--waveform-dir",
        type=Path,
        help="Separate directory for waveform files (default: same as output)"
    )
    
    # Processing options
    parser.add_argument(
        "-a", "--absolute-paths",
        action="store_true",
        help="Use absolute paths in wfdisc.dir field"
    )
    
    parser.add_argument(
        "--archive", "--zip",
        action="store_true",
        help="Create ZIP archive of CSS3.0 database"
    )
    
    parser.add_argument(
        "--plot", "--show-plot",
        action="store_true",
        help="Generate waveform plots"
    )
    
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Disable ObsPy stream cleanup"
    )
    
    # Logging options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors"
    )
    
    return parser


def setup_logging(verbose: bool = False, quiet: bool = False):
    """Setup logging configuration."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    
    # Update logger level
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)


def parse_args_to_config(args) -> ConversionConfig:
    """Convert argparse arguments to ConversionConfig."""
    config = ConversionConfig()
    
    # Input files
    config.mseed_file = args.input
    config.stationxml_file = args.stationxml
    
    # FDSN parameters
    config.fdsn_client = args.client
    config.username = args.user
    config.password = args.password
    config.timeout = args.timeout
    
    # Data selection
    config.network = args.net
    config.station = args.sta
    config.location = args.loc
    config.channel = args.chan
    config.starttime = args.starttime
    config.endtime = args.endtime
    config.record_length = args.length
    
    # Output options
    config.output_dir = args.output
    config.database_name = args.name
    config.waveform_dir = args.waveform_dir
    
    # Processing options
    config.use_absolute_paths = args.absolute_paths
    config.create_archive = args.archive
    config.show_plot = args.plot
    config.cleanup_data = not args.no_cleanup
    
    return config


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose, args.quiet)
    
    try:
        # Determine mode
        if len(sys.argv) == 1:
            # No arguments - interactive mode
            config = interactive_mode()
        else:
            # Command line mode
            config = parse_args_to_config(args)
            
            # Validate configuration
            if not config.mseed_file and not any([config.starttime, config.endtime, config.record_length]):
                logger.error("❌ For FDSN mode, specify at least starttime, endtime, or record length")
                sys.exit(1)
            
            if config.mseed_file and not config.mseed_file.exists():
                logger.error(f"❌ MiniSEED file not found: {config.mseed_file}")
                sys.exit(1)
            
            if config.stationxml_file and not config.stationxml_file.exists():
                logger.error(f"❌ StationXML file not found: {config.stationxml_file}")
                sys.exit(1)
        
        # Run conversion
        with CSS3Converter(config) as converter:
            success = converter.convert()
            
        if success:
            print(f"\n🎉 Conversion completed successfully!")
            print(f"📁 Results saved to: {config.output_dir}")
            sys.exit(0)
        else:
            print(f"\n❌ Conversion completed with errors!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n👋 Operation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()