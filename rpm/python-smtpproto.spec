Name:           python-smtpproto
Version:        2.0.0
Release:        1%{?dist}
Summary:        Sans-io SMTP client with an AnyIO based async I/O implementation

License:        MIT
URL:            https://github.com/agronholm/smtpproto
Source:         %{pypi_source smtpproto}

BuildArch:      noarch
BuildRequires:  python3-devel
%if 0%{?rhel} == 9
# smtpproto imports typing_extensions on Python < 3.10 but does not declare it
BuildRequires:  python3dist(typing-extensions)
%endif

%global _description %{expand:
This library contains a (client-side) sans-io implementation of the ESMTP
protocol. A concrete, asynchronous I/O implementation is also provided, via
the AnyIO library.

The following SMTP extensions are supported: 8BITMIME, AUTH, SIZE (max message
size reporting only), SMTPUTF8, STARTTLS.}

%description %_description

%package -n     python3-smtpproto
Summary:        %{summary}
%if 0%{?rhel} == 9
Requires:       python3dist(typing-extensions)
%endif

%description -n python3-smtpproto %_description


%prep
%autosetup -p1 -n smtpproto-%{version}
rm -rf src/*.egg-info

# set a static version instead of using setuptools_scm
sed -i \
    -e 's/^dynamic = \[ "version" \]$/version = "%{version}"/' \
    -e '/"setuptools_scm >= 6.4"/d' \
    pyproject.toml

%if 0%{?rhel} == 9
# setuptools 53 in EL9 does not support pyproject.toml (PEP 621 metadata), so
# we use hatchling instead.
# anyio 4 is not available but smtpproto (for mailqueue-runner) works fine with
# anyio 3.5.
sed -i \
    -e 's/"setuptools >= 64",/"hatchling",/' \
    -e 's/"setuptools.build_meta"/"hatchling.build"/' \
    -e 's/"anyio ~= 4.2"/"anyio >= 3.5"/' \
    pyproject.toml
%endif

# coverage is not needed to run the tests
%if 0%{?fedora}
%pyproject_patch_dependency coverage:ignore:br_only
%else
# EPEL does not provide %%pyproject_patch_dependency (yet)
sed -i '/"coverage >= 7",/d' pyproject.toml
%endif

%generate_buildrequires
%pyproject_buildrequires -x test


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files -l smtpproto


%check
%pytest


%files -n python3-smtpproto -f %{pyproject_files}
%doc README.rst docs/versionhistory.rst


%changelog
* Sun Sep 27 2026 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 2.0.0-1
- initial spec file
