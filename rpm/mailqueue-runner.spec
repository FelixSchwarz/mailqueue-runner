Name:           mailqueue-runner
Version:        0.10.0.20240805
Release:        1%{?dist}
Summary:        SMTP client for CLI scripts

License:        MIT
URL:            https://github.com/FelixSchwarz/mailqueue-runner
#Source:         %%{url}/archive/refs/tags/v%%{version}.tar.gz
Source:         mailqueue_runner-%{version}.tar.gz
Source1:        mailqueue-runner.conf

BuildArch:      noarch
BuildRequires:  python3-devel
# required to run the test suite
BuildRequires:  python3dist(pytest)
BuildRequires:  python3dist(pytest-xdist)
BuildRequires:  python3dist(testfixtures)


%global _description %{expand:
An SMTP client which provides a robust way to send email messages to an
external SMTP server.}

%description %_description

%prep
%autosetup -p1 -n mailqueue_runner-%{version}


%generate_buildrequires
%pyproject_buildrequires


%build
%pyproject_wheel


%install
%pyproject_install
/usr/bin/install --preserve-timestamps \
    --mode=0600 \
    -D --target-directory=%{buildroot}%{_sysconfdir} \
    %SOURCE1
/usr/bin/mkdir \
    --parents \
    --mode=0700 \
    %{buildroot}%{_localstatedir}/spool/mailqueue-runner

# https://bugzilla.redhat.com/show_bug.cgi?id=1935266
# namespace packages not fully supported ("schwarz/mailqueue" does not work)
%pyproject_save_files -l schwarz


%check
# not packaged at all
pip install pymta schwarzlog
# not packaged in EPEL 9
pip install time-machine dotmap
# tests requiring pymta just hang when run in mock (LATER: debug issue)
%pytest -n auto -k "not test_mq_send_test and not test_mq_sendmail and not test_can_send_message"


%post
restorecon %{_sysconfdir}/mailqueue-runner.conf

%files -f %{pyproject_files}
%doc README.md
%config(noreplace) %{_sysconfdir}/mailqueue-runner.conf
%{_bindir}/mq-run
%{_bindir}/mq-send-test
%{_bindir}/mq-sendmail
%dir %{_localstatedir}/spool/mailqueue-runner

%changelog
* Mon Aug 05 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.10.0.20240805-1
- initial spec file
