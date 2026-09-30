Name:           python-schwarzlog
Version:        0.7.0
Release:        1%{?dist}
Summary:        Library to add some missing functionality in Python's logging module

License:        MIT
URL:            https://github.com/FelixSchwarz/log_utils
Source:         %{pypi_source schwarzlog}

BuildArch:      noarch
BuildRequires:  python3-devel

%global _description %{expand:
Library to add some missing functionality in Python's "logging" module, e.g.
a logger which can be used without checking for "None", a logger which
forwards messages to another logger and helpers to collect log messages in
tests.}

%description %_description

%package -n     python3-schwarzlog
Summary:        %{summary}

%description -n python3-schwarzlog %_description


%prep
%autosetup -p1 -n schwarzlog-%{version}
rm -rf *.egg-info


%generate_buildrequires
%pyproject_buildrequires


%build
%pyproject_wheel


%install
%pyproject_install
# "schwarz" is a namespace package (shared e.g. with mailqueue-runner).
# "-L": setuptools 53 (EL9) does not record the license file in the metadata.
%pyproject_save_files -L schwarz


%check
# the sdist does not contain any tests
%py3_check_import schwarz.log_utils schwarz.log_utils.testutils


%files -n python3-schwarzlog -f %{pyproject_files}
%license LICENSE.txt
%doc README.md


%changelog
* Tue Sep 29 2026 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.7.0-1
- initial spec file
