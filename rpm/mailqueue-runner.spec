Name:           mailqueue-runner
Version:        0.13.1
Release:        1%{?dist}
Summary:        SMTP client for CLI scripts

License:        MIT
URL:            https://github.com/FelixSchwarz/mailqueue-runner
Source:         %pypi_source
Source1:        mailqueue-runner.conf
Source2:        mailqueue-runner.logrotate

Recommends:     logrotate

BuildArch:      noarch
BuildRequires:  python3-devel
# required to run the test suite
BuildRequires:  python3dist(pytest)
BuildRequires:  python3dist(pytest-xdist)
BuildRequires:  python3dist(testfixtures)
%if 0%{?fedora}
# only packaged for Fedora
BuildRequires:  python3dist(dotmap)
BuildRequires:  python3dist(time-machine)
%endif
Requires(post):    %{_sbindir}/alternatives
Requires(postun):  %{_sbindir}/alternatives

Provides: /usr/bin/mail
%if "%{_sbindir}" == "%{_bindir}"
# Compat symlinks for Requires in other packages.
# We rely on filesystem to create the symlinks for us.
Requires: filesystem(unmerged-sbin-symlinks)
Provides: /usr/sbin/sendmail
%endif


%global _description %{expand:
An SMTP client which provides a robust way to send email messages to an
external SMTP server.}

%description %_description

%prep
%autosetup -p1 -n mailqueue-runner-%{version}
rm -rf *.egg-info

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
    %{buildroot}%{_localstatedir}/spool/mailqueue-runner/{new,cur,tmp}
/usr/bin/mkdir \
    --parents \
    --mode=0700 \
    %{buildroot}%{_localstatedir}/log/mailqueue-runner
/usr/bin/install --preserve-timestamps \
    --mode=0644 \
    -D \
    %{SOURCE2} \
    %{buildroot}/%{_sysconfdir}/logrotate.d/mailqueue-runner.conf


# https://bugzilla.redhat.com/show_bug.cgi?id=1935266
# namespace packages not fully supported ("schwarz/mailqueue" does not work)
%pyproject_save_files -l schwarz


%check
# not packaged at all
pip install pymta schwarzlog
%if 0%{?rhel}
# not packaged in EPEL 9
pip install time-machine dotmap
%endif

# tests requiring pymta just hang when run in mock (LATER: debug issue)
%pytest -n auto -k "not test_mq_send_test and not test_mq_sendmail and not test_can_send_message and not test_mq_mail"


%post
# set -x
restorecon %{_sysconfdir}/mailqueue-runner.conf
# using two different alternatives allows the administrator to use some other
# software alongside mailqueue-runner. For example "msmtp" provides a "sendmail"
# alternative so with two alternatives, we can still provide "/usr/bin/mail".
%{_sbindir}/alternatives --install %{_sbindir}/sendmail mta %{_bindir}/mq-sendmail 30
%{_sbindir}/alternatives --install %{_bindir}/mail mail %{_bindir}/mq-mail 30 \
    --slave %{_bindir}/mailx mailx %{_bindir}/mq-mail


%postun
# set -x
if [ $1 -eq 0 ] ; then
    %{_sbindir}/alternatives --remove mta %{_bindir}/mq-sendmail
    %{_sbindir}/alternatives --remove mail %{_bindir}/mq-mail
fi


%files -f %{pyproject_files}
%doc README.md
%config(noreplace) %{_sysconfdir}/mailqueue-runner.conf
%dir %{_sysconfdir}/logrotate.d
%config(noreplace) %{_sysconfdir}/logrotate.d/mailqueue-runner.conf
%{_bindir}/mq-mail
%{_bindir}/mq-run
%{_bindir}/mq-send-test
%{_bindir}/mq-sendmail
%ghost %{_bindir}/mail
%ghost %{_bindir}/mailx
%if "%{_sbindir}" == "%{_bindir}"
%ghost %{_bindir}/sendmail
%else
%ghost %{_sbindir}/sendmail
%endif
%dir %{_localstatedir}/spool/mailqueue-runner
%dir %{_localstatedir}/spool/mailqueue-runner/new
%dir %{_localstatedir}/spool/mailqueue-runner/cur
%dir %{_localstatedir}/spool/mailqueue-runner/tmp
%dir %{_localstatedir}/log/mailqueue-runner


%changelog
* Mon Jun 02 2025 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.13.0-2
- update to 0.13.1

* Fri Oct 18 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.13.0-1
- update to 0.13.0

* Sun Sep 15 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.12.1-1
- update to 0.12.1

* Sun Sep 01 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.12.0-1
- update to 0.12.0

* Wed Aug 07 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.11.0-1
- update to 0.11.0

* Mon Aug 05 2024 Felix Schwarz <felix.schwarz@oss.schwarz.eu> - 0.10.0.20240805-1
- initial spec file
