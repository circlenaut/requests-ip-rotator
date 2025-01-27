# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]
### Changed

- Restructured project
  - created `src` directory: moved project code here
- Added single leading underscores to the private methods of `ApiGateway` :
  - `init_gateway`, `send`, `delete_gateway`

### Added
- CI/CD: Transitioned away from `setup.py`
  - configured `pyproject.toml`
  - configured `setup.cfg`
- CI/CD: created environment files
  - `environemnt.yaml` : for created conda environment
  - `requirements.txt` : for installing pip dependencies
- tests: created files to quickly test iterations under the `tests` directory
    - `test.py` : Loads package and prints version
    - `test.sh` : Reinstalls package and runs `test.py`
- examples: created a sample file to quickly assess this project under the `examples` directory
  - `sample.py` : An example file showcasing how to use this package
  - `credentials-sample.json`: A sample json file to store your aws IAM credentials
- logging: replaced all print statements with a logger
- Created an `AWS` class to manage client connections

### Removed
- `setup.py`


## [1.0.9] - 2021-09-03
### Added

- Forked repo: https://github.com/Ge0rg3/requests-ip-rotator

Thanks @Ge0rg3