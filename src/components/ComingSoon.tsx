interface Props {
  title: string;
  note: string;
}

export function ComingSoon({ title, note }: Props) {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-8 text-center">
      <div className="text-2xl font-bold mb-2">{title}</div>
      <div className="text-slate-400 text-sm max-w-xl mx-auto">{note}</div>
      <div className="text-xs text-slate-500 mt-4 mono">
        TODO: migrate from legacy index.html
      </div>
    </div>
  );
}
