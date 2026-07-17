"""Create the institutional knowledge_base directory tree with markdown sources."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "knowledge_base"

FILES: dict[str, str] = {
    "admissions/admissions_handbook.md": """# Admissions Handbook

## Overview
This handbook describes undergraduate and postgraduate admission to the institution.

## Eligibility
- Undergraduate: completion of 10+2 or equivalent with minimum aggregate as per program brochure.
- Postgraduate: recognized bachelor's degree in a relevant discipline.

## Application Channels
Applications are accepted online through the official admissions portal. Offline forms are not accepted.

## Selection Process
Merit lists are prepared using entrance examination scores, academic records, and category reservations as per government norms.

## Document Verification
Original certificates must be presented during verification. Provisional admission is cancelled if documents are found invalid.
""",
    "admissions/admission_process.md": """# Admission Process

## Step 1 — Register Online
Create an account on the admissions portal and complete the application form.

## Step 2 — Upload Documents
Upload mark sheets, identity proof, category certificate (if applicable), and photograph.

## Step 3 — Pay Application Fee
The non-refundable application fee must be paid online. Payment confirmation is required to submit the form.

## Step 4 — Entrance Examination / Merit
Appear for the prescribed entrance test or await merit-based selection as per program rules.

## Step 5 — Counselling and Seat Allotment
Selected candidates attend counselling, choose program and specialization, and pay admission fee.

## Step 6 — Reporting to Campus
Report on the notified date with originals for verification and hostel allotment (if requested).
""",
    "admissions/admission_checklist.md": """# Admission Checklist

Before reporting to campus, ensure you have:

- [ ] Admission offer letter (printout)
- [ ] 10th and 12th mark sheets and certificates
- [ ] Transfer certificate / migration certificate (if applicable)
- [ ] Character certificate
- [ ] Category / reservation certificates (if applicable)
- [ ] Medical fitness certificate
- [ ] Passport-size photographs (6 copies)
- [ ] Aadhaar / government ID proof
- [ ] Fee payment receipts
- [ ] Hostel application form (if staying on campus)
""",
    "admissions/admission_policies.md": """# Admission Policies

## Reservation Policy
Seats are reserved for SC, ST, OBC, EWS, and PwD categories as per applicable government regulations.

## Cancellation Policy
Withdrawal before the last date of admission may receive partial refund of tuition fee as per the fee refund policy.

## Anti-Ragging Undertaking
All admitted students and parents must sign the anti-ragging undertaking before enrollment.

## Duplicate Admission
A student admitted to this institution may not hold simultaneous admission in another degree program without prior approval.
""",
    "admissions/admission_faq.md": """# Admissions FAQ

**When do applications open?**
Applications typically open in April for the July intake. Check the admissions portal for exact dates.

**Can I change my program after admission?**
Program changes are permitted only before the last date of registration, subject to seat availability and approval.

**Is hostel guaranteed?**
Hostel allotment is on a first-come, first-served basis after fee payment. It is not guaranteed with admission.

**How do I track application status?**
Log in to the admissions portal using your application ID.
""",
    "scholarships/scholarship_handbook.md": """# Scholarship Handbook

## Purpose
Scholarships recognize academic merit, financial need, sports achievement, and category-based support.

## Types of Scholarships
- Merit scholarships for top rank holders
- Need-based financial aid
- Government scholarships (state and central)
- Sports and cultural excellence awards

## Disbursement
Approved scholarships are credited to the student fee account or bank account as per scheme rules.
""",
    "scholarships/scholarship_eligibility.md": """# Scholarship Eligibility

## Merit Scholarships
- Minimum CGPA of 8.0 in the previous academic year (continuing students)
- Top 5% of incoming batch (new admissions)

## Need-Based Aid
- Family income below the threshold declared annually by the Financial Aid Desk
- Satisfactory academic progress (no backlogs in more than two courses)

## Government Schemes
Eligibility follows respective state/central scheme guidelines. Students must apply through the prescribed portal.

## Renewal
Scholarships are renewed each year subject to attendance (75% minimum) and CGPA requirements.
""",
    "scholarships/scholarship_application.md": """# Scholarship Application

## Application Window
Need-based scholarship applications open in August each year.

## How to Apply
1. Complete the online scholarship form on the student portal.
2. Upload income certificate, bank details, and previous mark sheets.
3. Submit before the published deadline.

## Contact
Financial Aid Desk — finaid@college.edu
""",
    "scholarships/scholarship_policies.md": """# Scholarship Policies

## Verification
All documents are verified. False declarations lead to cancellation of scholarship and disciplinary action.

## Partial Attendance
Students with attendance below 75% are not eligible for renewal unless condonation is officially granted.

## Concurrent Awards
A student may receive only one institutional merit award. Government schemes may be combined as per rules.
""",
    "scholarships/scholarship_faq.md": """# Scholarship FAQ

**When are results announced?**
Merit lists are published within four weeks of the application deadline.

**Can I apply if I have a backlog?**
Need-based aid requires no more than two backlogs. Merit scholarships require a clear academic record.

**Are hostel fee waivers included?**
Some schemes cover tuition only. Check individual scheme details on the portal.
""",
    "fees/fee_structure.md": """# Fee Structure

## Tuition Fee
Undergraduate programs: as per the approved fee committee schedule published each academic year.
Postgraduate programs: published separately in the program brochure.

## Hostel Fee
- Undergraduate shared room: INR 60,000 per academic year
- Postgraduate single room: INR 85,000 per academic year

## Examination Fee
End-semester examination fee is charged per subject at the time of registration.

## Other Charges
Laboratory, library, and student activity fees are listed in the semester fee statement.
""",
    "fees/payment_methods.md": """# Fee Payment Methods

## Online Payment
Pay through the student ERP portal using net banking, UPI, debit card, or credit card.

## Installments
Tuition and hostel fees may be paid in two installments per academic year as notified.

## Challan / Bank Deposit
Offline challan generation is available on the portal for designated bank branches.

## Receipts
Always download and retain the payment receipt from the portal for your records.
""",
    "fees/refund_policy.md": """# Fee Refund Policy

## Withdrawal Within 15 Days
Partial refund of tuition fee may be granted after deducting administrative charges.

## Hostel Refund
Students withdrawing from hostel within 15 days of allotment may receive a partial hostel fee refund after deducting one month's charges. No refund after 15 days except on medical grounds approved by the Dean of Student Affairs.

## Security Deposit
Hostel security deposit of INR 10,000 is refundable on vacating, minus damage charges.

## Examination Fee
Examination fees are non-refundable after the registration deadline.
""",
    "fees/late_fee_policy.md": """# Late Fee Policy

## Tuition Fee
Late payment of semester fee attracts a fine as notified in the academic calendar.

## Hostel Fee
Late hostel fee payment attracts INR 100 per day, up to a maximum of INR 5,000.

## Examination Registration
Late registration for examinations incurs a prescribed late fee per subject.
""",
    "fees/fee_faq.md": """# Fee FAQ

**Where do I see my fee statement?**
Log in to the student ERP portal under Finance → Fee Statement.

**Can fees be paid in cash?**
Cash payments are not accepted at the accounts office. Use online or bank challan methods.

**Is mess fee included in hostel fee?**
No. Mess charges are separate. Monthly mess advance is INR 4,500.
""",
    "academics/academic_regulations.md": """# Academic Regulations

## Credit System
Programs follow a credit-based semester system. Students must earn the prescribed credits to graduate.

## Course Registration
Students register for courses during the first two weeks of each semester through the ERP portal.

## Minimum Progress
Students must maintain satisfactory academic progress as defined by the academic senate.
""",
    "academics/attendance_policy.md": """# Attendance Policy

Students must maintain a minimum of **75% attendance** in each course to be eligible for the end-semester examination.

Students with attendance between **65% and 75%** may apply for condonation through the Head of Department, subject to valid medical or documented reasons.

Attendance is recorded for lectures, tutorials, and laboratory sessions separately where applicable.
""",
    "academics/grading_system.md": """# Grading System

## Letter Grades
Courses are graded on a 10-point scale: O, A+, A, B+, B, C, P, F.

## Grade Points
Grade points are used to compute SGPA and CGPA each semester.

## Fail Grade
Grade F indicates failure. Students must register for supplementary examination or repeat the course as prescribed.
""",
    "academics/credit_system.md": """# Credit System

## Definition
One credit typically represents one hour of instruction per week over a semester.

## Minimum Credits
Undergraduate programs require completion of prescribed core, elective, and open elective credits.

## Audit Courses
Audit registration is permitted for selected courses without grade points, subject to seat availability.
""",
    "academics/academic_faq.md": """# Academic FAQ

**How do I apply for attendance condonation?**
Submit the condonation form with supporting documents to your department within one week of the announced deadline.

**What is the passing grade?**
Grade P or above is required to pass a course.

**Can I overload credits?**
Overload beyond the prescribed maximum requires advisor and HOD approval.
""",
    "examinations/examination_handbook.md": """# Examination Handbook

## Examination Types
- Mid-semester tests (internal)
- End-semester examinations
- Practical and viva examinations
- Supplementary examinations

## Registration
All students must register for examinations through the ERP portal before the deadline.

## Hall Tickets
Hall tickets are issued only after fee clearance and attendance eligibility verification.
""",
    "examinations/examination_rules.md": """# Examination Rules

## Conduct
Students must carry hall ticket and college ID. Electronic devices are prohibited in examination halls unless explicitly permitted.

## Timing
Students must be seated 15 minutes before the scheduled start. Late entry is not permitted after 30 minutes.

## Materials
Only permitted stationery and calculators (if allowed) may be brought into the hall.
""",
    "examinations/revaluation_policy.md": """# Revaluation Policy

Students may apply for revaluation of end-semester answer scripts within **10 working days** of result publication.

The revaluation fee is **INR 500 per subject**.

The revaluation result is final and binding.
""",
    "examinations/malpractice_policy.md": """# Malpractice Policy

## Prohibited Acts
Copying, possession of unauthorized material, impersonation, and disruption of examination are malpractice.

## Penalties
Penalties range from cancellation of the paper to suspension or expulsion depending on severity.

## Appeals
Appeals must be filed in writing to the Controller of Examinations within the notified period.
""",
    "examinations/examination_faq.md": """# Examination FAQ

**When are supplementary exams held?**
Usually in July, once per year. Register and pay the fee before the deadline.

**How do I get my hall ticket?**
Download from the ERP portal after examination registration is confirmed.

**What if I am medically unfit to write an exam?**
Submit medical certificate and application for special consideration to the examination section.
""",
    "academic_calendar/semester_schedule.md": """# Semester Schedule

The academic year consists of two semesters:

- **Odd Semester:** July to December
- **Even Semester:** January to June

Each semester includes approximately 16 weeks of instruction followed by end-semester examinations.
""",
    "academic_calendar/important_dates.md": """# Important Dates

## Typical Academic Timeline
- Course registration: first two weeks of semester
- Mid-semester examinations: week 8
- End-semester examinations: after week 16
- Result publication: within four weeks of last examination
- Supplementary examinations: July

Exact dates are published in the official academic calendar on the portal each year.
""",
    "academic_calendar/academic_calendar_faq.md": """# Academic Calendar FAQ

**Where is the official calendar published?**
On the institution website and student ERP portal under Academics → Calendar.

**Are holidays included in the 16 teaching weeks?**
National and institutional holidays are excluded from instructional days.

**Do examination weeks extend the semester?**
Examination period is scheduled after the instructional weeks and does not reduce teaching days.
""",
    "hostel/hostel_handbook.md": """# Hostel Handbook

## Overview
Campus hostels provide safe accommodation for enrolled students. Allotment is subject to availability and fee payment.

## Room Types
- Undergraduate: shared double-occupancy rooms
- Postgraduate: single-occupancy rooms (where available)

## Warden Office
The warden office handles allotment, leave, discipline, and maintenance requests.
""",
    "hostel/hostel_rules.md": """# Hostel Rules

## Timings
Hostel gates close at 10:00 PM on weekdays and 11:00 PM on weekends unless prior permission is granted.

## Visitors
Visitors are allowed only in designated areas during visiting hours with ID verification.

## Prohibited Items
Cooking appliances, hazardous materials, and illegal substances are strictly prohibited.
""",
    "hostel/hostel_leave_policy.md": """# Hostel Leave Policy

## Local Leave
Apply through the hostel portal or warden office at least 24 hours in advance.

## Overnight Leave
Parent/guardian consent is required for overnight leave. Submit the leave form to the warden.

## Emergency Leave
Inform the warden and security immediately in emergencies and submit documentation on return.
""",
    "hostel/mess_policy.md": """# Mess Policy

Mess charges are separate from the hostel fee.

The monthly mess advance is **INR 4,500**.

Unused mess balance at the end of the semester may be adjusted against the next semester, subject to mess committee rules.

Menu and timing are displayed on the mess notice board.
""",
    "hostel/hostel_facilities.md": """# Hostel Facilities

## Included
Basic furniture, common washrooms, study areas, and Wi-Fi in designated zones.

## Laundry
Coin-operated laundry facilities are available in each hostel block.

## Medical
First-aid kits are available at the warden office. Serious cases are referred to the campus medical center.
""",
    "hostel/hostel_faq.md": """# Hostel FAQ

**What is the annual hostel fee?**
INR 60,000 for undergraduate shared rooms; INR 85,000 for postgraduate single rooms.

**Is there a security deposit?**
Yes. INR 10,000 refundable deposit at allotment.

**Can I change my room?**
Room changes are considered only for documented medical or safety reasons, subject to availability.
""",
    "library/library_handbook.md": """# Library Handbook

## Mission
The central library supports teaching, learning, and research with print and digital collections.

## Membership
All enrolled students are automatic members. Use your student ID for access and borrowing.

## Floors
Ground floor: circulation desk and new arrivals. Upper floors: reading halls and reference section.
""",
    "library/borrowing_policy.md": """# Borrowing Policy

## Limits
- Undergraduate students: up to 4 books for 14 days
- Postgraduate students: up to 6 books for 21 days
- Faculty: up to 10 books for 30 days

## Non-Borrowable Items
Reference books, journals, and rare collections must be used inside the library only.
""",
    "library/digital_resources.md": """# Digital Resources

Students can access IEEE Xplore, SpringerLink, and JSTOR through the campus network or library VPN.

Login credentials are the same as the student portal credentials.

E-books and past question papers are available on the library portal.
""",
    "library/membership_policy.md": """# Library Membership Policy

Membership is valid for the duration of enrollment.

Alumni may apply for limited borrowing privileges with an alumni card and deposit.

Loss of student ID must be reported immediately to block unauthorized borrowing.
""",
    "library/library_faq.md": """# Library FAQ

**What are the opening hours?**
Monday–Friday 8:00 AM–10:00 PM; Saturday 9:00 AM–6:00 PM. Closed Sundays except during examination weeks (10:00 AM–4:00 PM).

**What is the overdue fine?**
INR 5 per day per book.

**Can I eat in the library?**
Food and beverages are not allowed in reading halls.
""",
    "student_services/counseling_services.md": """# Counseling Services

The Student Counseling Center provides confidential counseling for academic stress, personal concerns, and mental health support.

Appointments can be booked through the student portal or by visiting Room B-12 in the Student Services Building.

Walk-in hours are Monday to Friday, 10:00 AM to 4:00 PM.

Crisis counseling helpline is available 24x7.
""",
    "student_services/placement_cell.md": """# Placement Cell

The Placement Cell coordinates campus recruitment, internships, and career workshops.

Students must register on the placement portal and complete resume verification.

Eligibility criteria for drives are published per company notification.
""",
    "student_services/health_services.md": """# Health Services

The campus medical center (Room G-01) is open 24 hours for emergencies and routine consultations during daytime hours.

Students should carry their ID for treatment records.

Vaccination camps and health awareness programs are conducted each semester.
""",
    "student_services/grievance_redressal.md": """# Grievance Redressal

Students may submit academic or administrative grievances through the online grievance portal.

Grievances are acknowledged within 3 working days and resolved as per the grievance committee schedule.

Anonymous complaints are accepted for sensitive matters.
""",
    "student_services/student_services_faq.md": """# Student Services FAQ

**How do I meet my academic advisor?**
Each student is assigned a faculty advisor. Meet at least once per semester. Book slots through the department office.

**Where is the Financial Aid Desk?**
Student Services Building, ground floor. Email: finaid@college.edu

**How do I request disability accommodations?**
Submit documented requests at least two weeks before the relevant assessment to the Disability Support office.
""",
    "erp/erp_login_guide.md": """# ERP Login Guide

## Portal URL
Access the student ERP at the link provided on the institution website.

## Credentials
Username: your enrollment number. Initial password is sent to your registered email after admission.

## First Login
Change your password immediately and set security questions.

## Modules
Academics, finance, hostel, library, and examination modules are available after enrollment activation.
""",
    "erp/password_reset.md": """# Password Reset

## Self-Service Reset
Click "Forgot Password" on the ERP login page. Enter enrollment number and registered email or mobile.

## OTP Verification
A one-time password is sent to your registered contact. OTP expires in 10 minutes.

## Helpdesk
If reset fails, visit the IT helpdesk with your college ID during office hours.
""",
    "erp/portal_features.md": """# Portal Features

- Course registration and timetable
- Fee payment and receipts
- Examination registration and hall tickets
- Hostel and mess applications
- Scholarship applications
- Grievance submission
- Library account and digital resource links
""",
    "erp/erp_faq.md": """# ERP FAQ

**I cannot see my courses after login.**
Complete fee payment and wait up to 24 hours for enrollment sync. Contact the department if the issue persists.

**Can parents access the portal?**
A limited parent view is available for fee payment with student authorization.

**Is the portal available on mobile?**
Yes. Use a modern browser or the official mobile-friendly portal link.
""",
    "certificates/bonafide_certificate.md": """# Bonafide Certificate

## Purpose
Proof of enrollment for banks, scholarships, and external applications.

## Application
Apply through ERP → Certificates → Bonafide. Processing time: 3 working days.

## Fee
Nominal fee as per accounts notification. Collect from the academic section.
""",
    "certificates/transcript_request.md": """# Transcript Request

Official transcripts list courses and grades earned.

Apply online with purpose and number of copies required.

Processing time is 7–10 working days. Expedited service may be available for alumni.
""",
    "certificates/migration_certificate.md": """# Migration Certificate

Required when transferring to another university.

Apply after clearing all dues and obtaining no-objection from the department.

Submit leaving certificate and ID copy with the application form.
""",
    "certificates/provisional_degree.md": """# Provisional Degree Certificate

Issued after completion of all degree requirements pending convocation.

Apply through the examination section after final result publication.

Valid until the convocation degree is issued.
""",
    "certificates/certificates_faq.md": """# Certificates FAQ

**How long do certificates take?**
Bonafide: 3 days. Transcript: 7–10 days. Degree: after convocation schedule.

**Can I authorize someone to collect?**
Yes, with a signed authorization letter and copy of your ID.
""",
    "policies/anti_ragging_policy.md": """# Anti-Ragging Policy

Ragging in any form is prohibited and punishable under law and institutional rules.

All students sign an anti-ragging undertaking at admission.

Report incidents to the anti-ragging helpline or warden immediately. Identity of reporters is protected.
""",
    "policies/code_of_conduct.md": """# Code of Conduct

Students must behave respectfully toward peers, faculty, and staff.

Damage to institutional property, harassment, and academic dishonesty violate the code of conduct.

Violations are referred to the disciplinary committee.
""",
    "policies/disciplinary_policy.md": """# Disciplinary Policy

Penalties include warning, fine, suspension, and expulsion depending on severity.

Students have the right to present their case before the disciplinary committee.

Decisions are communicated in writing with appeal procedures.
""",
    "policies/privacy_policy.md": """# Privacy Policy

Personal data collected during admission and enrollment is used for academic and administrative purposes only.

Data is not shared with third parties except as required by law or with student consent.

Students may request correction of inaccurate records through the ERP helpdesk.
""",
    "policies/campus_safety.md": """# Campus Safety

Security personnel patrol campus 24x7.

Emergency internal number: **100**. External medical emergency: contact campus medical center Room G-01.

Report suspicious activity to security immediately. CCTV is operational in common areas.
""",
    "policies/policies_faq.md": """# Policies FAQ

**Where do I report harassment?**
Student Services grievance portal or the designated harassment redressal officer.

**Are guests allowed on campus?**
Guests must register at the security gate and be accompanied by a student or staff member in academic blocks.
""",
    "contacts/departments.md": """# Department Contacts

## Admissions Office
admissions@college.edu | Extension 101

## Accounts / Finance
accounts@college.edu | Extension 102

## Examination Section
exams@college.edu | Extension 103

## Hostel Office
hostel@college.edu | Extension 104

## Library
library@college.edu | Extension 105
""",
    "contacts/emergency_contacts.md": """# Emergency Contacts

Campus Security (internal): **100**
Campus Security (external): +91-XXXXXXXXXX

Medical Center: Room G-01 — open 24 hours

Counseling Helpline: available 24x7 for crisis support

Fire emergency: activate nearest alarm and call security
""",
    "contacts/office_hours.md": """# Office Hours

## Student Services Building
Monday–Friday: 9:00 AM – 5:00 PM
Saturday: 9:00 AM – 1:00 PM (selected counters only)

## Accounts Office
Monday–Friday: 10:00 AM – 4:00 PM

## Library
See library handbook for detailed timings.

Holidays follow the institutional academic calendar.
""",
    "campus_facilities/transport.md": """# Campus Transport

Shuttle buses connect hostels, academic blocks, and the main gate on a fixed schedule.

Bus passes are issued at the transport office at the start of each semester.

Timings are posted at hostel notice boards and on the portal.
""",
    "campus_facilities/sports.md": """# Sports Facilities

Facilities include cricket ground, basketball courts, indoor badminton, and gymnasium.

Students must register for sports slots through the sports office.

Inter-college participation requires NOC from the department and sports coordinator.
""",
    "campus_facilities/cafeteria.md": """# Cafeteria

The main cafeteria serves breakfast, lunch, and snacks on weekdays.

Payment by student ID card or UPI. Outside food delivery is not permitted in academic blocks.

Hygiene inspections are conducted monthly.
""",
    "campus_facilities/wi_fi.md": """# Campus Wi-Fi

Wi-Fi is available in academic buildings, library, and designated hostel zones.

Connect using enrollment number and ERP password.

Misuse of network for illegal downloads may lead to account suspension.
""",
    "campus_facilities/facilities_faq.md": """# Facilities FAQ

**Is parking available?**
Two-wheeler parking is available for students with valid permit stickers.

**Are laundry services in hostel?**
Yes. Coin-operated machines in each block.

**Can I use the gym without a sports registration?**
Gym access requires a one-time registration and health declaration at the sports office.
""",
    "general_faq/student_life.md": """# Student Life

Clubs and societies cover technical, cultural, and social activities.

Freshers' orientation is held in the first week of the odd semester.

Hostel and day scholars participate equally in campus events subject to registration.
""",
    "general_faq/onboarding.md": """# Student Onboarding

## Week 1
Complete ERP activation, ID card collection, and department induction.

## Week 2
Course registration and library orientation.

## Support
Academic advisors, counselors, and the student helpdesk assist with onboarding queries.
""",
    "general_faq/general_faq.md": """# General FAQ

**Where do I get my ID card?**
Collect from the administration block after photograph submission during onboarding.

**How do I update my contact details?**
Update through ERP → Profile. Keep mobile and email current for official notices.

**Who helps with fee or hostel questions?**
Accounts office for fees; hostel office for accommodation; Financial Aid Desk for scholarships.
""",
}


def main() -> None:
    KB.mkdir(parents=True, exist_ok=True)
    for rel_path, content in sorted(FILES.items()):
        path = KB / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
    (KB / ".gitkeep").write_text("", encoding="utf-8")
    print(f"Created {len(FILES)} knowledge base files under {KB}")


if __name__ == "__main__":
    main()
