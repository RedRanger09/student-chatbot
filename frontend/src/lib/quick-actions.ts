import type { LucideIcon } from "lucide-react";
import {
  Bed,
  Bell,
  BookOpen,
  Building2,
  Calendar,
  FileText,
  GraduationCap,
  HelpCircle,
  IdCard,
  KeyRound,
  Library,
  MapPin,
  Scale,
  ShieldCheck,
  Wallet,
} from "lucide-react";

export type QuickAction = {
  id: string;
  label: string;
  description: string;
  prompt: string;
  icon: LucideIcon;
};

export const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "admissions",
    label: "Admissions",
    description: "Applications & intake",
    prompt: "How do I apply for admission?",
    icon: GraduationCap,
  },
  {
    id: "scholarships",
    label: "Scholarships",
    description: "Aid & eligibility",
    prompt: "What scholarships are available?",
    icon: Wallet,
  },
  {
    id: "fees",
    label: "Fees",
    description: "Payments & deadlines",
    prompt: "How do I pay my tuition fees?",
    icon: Wallet,
  },
  {
    id: "academics",
    label: "Academics",
    description: "Courses & advising",
    prompt: "Tell me about academic advising and course registration.",
    icon: BookOpen,
  },
  {
    id: "examination",
    label: "Examination",
    description: "Exams & results",
    prompt: "Tell me about exam registration.",
    icon: FileText,
  },
  {
    id: "calendar",
    label: "Academic Calendar",
    description: "Dates & holidays",
    prompt: "What are the important dates in the academic calendar?",
    icon: Calendar,
  },
  {
    id: "hostel",
    label: "Hostel",
    description: "Housing & mess",
    prompt: "Tell me about hostel facilities.",
    icon: Bed,
  },
  {
    id: "library",
    label: "Library",
    description: "Hours & borrowing",
    prompt: "What are the library timings?",
    icon: Library,
  },
  {
    id: "student-services",
    label: "Student Services",
    description: "Support & counseling",
    prompt: "What student support services are available on campus?",
    icon: ShieldCheck,
  },
  {
    id: "erp",
    label: "ERP / Login Help",
    description: "Portal access",
    prompt: "I need help logging into the student ERP portal.",
    icon: KeyRound,
  },
  {
    id: "certificates",
    label: "Certificates",
    description: "Requests & letters",
    prompt: "How do I request an official certificate or transcript?",
    icon: IdCard,
  },
  {
    id: "policies",
    label: "Policies",
    description: "Rules & guidelines",
    prompt: "What are the important student policies I should know?",
    icon: Scale,
  },
  {
    id: "contacts",
    label: "Contacts",
    description: "Offices & helplines",
    prompt: "Who should I contact for student support?",
    icon: Bell,
  },
  {
    id: "facilities",
    label: "Campus Facilities",
    description: "Spaces & amenities",
    prompt: "What campus facilities are available for students?",
    icon: Building2,
  },
  {
    id: "faqs",
    label: "General FAQs",
    description: "Common questions",
    prompt: "What are the most common questions new students ask?",
    icon: HelpCircle,
  },
  {
    id: "map",
    label: "Getting Around",
    description: "Campus navigation",
    prompt: "How do I find key buildings and services on campus?",
    icon: MapPin,
  },
];
