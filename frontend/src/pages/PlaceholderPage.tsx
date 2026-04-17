interface Props {
  title: string;
}

export default function PlaceholderPage({ title }: Props) {
  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
      <p className="mt-2 text-gray-500">Coming soon.</p>
    </div>
  );
}
