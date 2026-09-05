export const mockStudent = {
  name: "Student",
  email: "",
  department: "Computer Science",
  year: "3rd Year",
  role: "student"
};

export const moods = [
  { id: "great", label: "Great", icon: "✨", score: 1 },
  { id: "okay", label: "Okay", icon: "🙂", score: 2 },
  { id: "low", label: "Low", icon: "🌧️", score: 3 },
  { id: "stressed", label: "Stressed", icon: "😣", score: 4 }
];

export const games = [
  { id: "breath", title: "Box Breathing", description: "A guided breathing reset for a calmer moment.", duration: "2 min", tag: "Calm", icon: "Wind" },
  { id: "focus", title: "Focus Sprint", description: "Find the different symbol and give your attention a quick reset.", duration: "1 min", tag: "Focus", icon: "Target" },
  { id: "memory", title: "Mind Match", description: "Match pairs to gently engage your memory and attention.", duration: "2 min", tag: "Memory", icon: "Brain" },
  { id: "calmcolors", title: "Color Calm", description: "Follow a soft color sequence and slow your attention down.", duration: "1 min", tag: "Calm", icon: "Sparkles" },
  { id: "moodgarden", title: "Mood Garden", description: "Grow a tiny virtual garden through positive prompts.", duration: "2 min", tag: "Reflect", icon: "Heart" },
  { id: "meditation", title: "Mini Meditation", description: "A short guided pause with breathing, noticing and gentle attention.", duration: "3 min", tag: "Meditate", icon: "Wind" }
];

export const insights = [
  { label: "Mood stability", value: 76, change: "+8%" },
  { label: "Stress level", value: 42, change: "-12%" },
  { label: "Check-in consistency", value: 88, change: "+14%" }
];

export const counselors = [
  { id: "c1", name: "Dr. Meera Sharma", role: "Student Counselor", specialty: "General wellbeing", availability: "Available today", email: "counselor@campus.edu", phone: "+91 90000 10001" },
  { id: "c2", name: "Rahul Verma", role: "Wellbeing Counselor", specialty: "Academic stress", availability: "Available today", email: "wellbeing@campus.edu", phone: "+91 90000 10002" },
  { id: "c3", name: "Dr. Nisha Kapoor", role: "Counselor", specialty: "Personal support", availability: "Available tomorrow", email: "support@campus.edu", phone: "+91 90000 10003" }
];

export const departments = [
  { name: "Computer Science & Eng", students: 420, stable: 315, moderate: 75, priority: 30, stress: 6.8, change: "-3.4%", tone: "priority" },
  { name: "Mechanical Engineering", students: 310, stable: 248, moderate: 48, priority: 14, stress: 5.9, change: "-1.2%", tone: "moderate" },
  { name: "Electronics & Comm", students: 380, stable: 280, moderate: 72, priority: 28, stress: 7.1, change: "-4.8%", tone: "priority" },
  { name: "Business Management", students: 250, stable: 215, moderate: 27, priority: 8, stress: 4.8, change: "+0.6%", tone: "stable" },
  { name: "Biotechnology", students: 190, stable: 158, moderate: 24, priority: 8, stress: 5.2, change: "+1.1%", tone: "moderate" },
  { name: "Civil Engineering", students: 220, stable: 194, moderate: 21, priority: 5, stress: 4.5, change: "+0.4%", tone: "stable" }
];

export const priorityStudents = [
  { id: "CP-1003", name: "Student 1003", department: "Computer Science & Engineering", year: "1st Year", score: "1.8/10", priority: "Stable Signal", trend: "Improving", note: "Routine check-ins consistent" },
  { id: "CP-2048", name: "Student 2048", department: "Computer Science & Engineering", year: "3rd Year", score: "8.4/10", priority: "Priority Counselor Review", trend: "Declining", note: "Repeated high-stress signals" },
  { id: "CP-3127", name: "Student 3127", department: "Mechanical Engineering", year: "2nd Year", score: "6.8/10", priority: "Moderate Support Need", trend: "Declining", note: "Support pathway active" },
  { id: "CP-4211", name: "Student 4211", department: "Business Management", year: "1st Year", score: "3.2/10", priority: "Stable Signal", trend: "Improving", note: "Healthy routine trend" },
  { id: "CP-5086", name: "Student 5086", department: "Electronics & Communication", year: "4th Year", score: "7.6/10", priority: "Priority Counselor Review", trend: "Declining", note: "Follow-up recommended" }
];
