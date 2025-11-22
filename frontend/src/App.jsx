import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Activity, Users, AlertCircle } from 'lucide-react';

// Función que hace la petición a la API
const fetchTecnicos = async () => {
  const { data } = await axios.get('/api/v1/tecnicos/');
  return data;
};

export default function App() {
  // Usamos React Query para manejar la petición (carga, error, data)
  const { data: tecnicos, isLoading, isError, error } = useQuery({
    queryKey: ['tecnicos'],
    queryFn: fetchTecnicos,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-blue-400 text-xl animate-pulse flex items-center gap-2">
          <Activity className="h-6 w-6" /> Cargando datos...
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-red-400 text-xl flex items-center gap-2 bg-red-900/20 p-4 rounded-lg border border-red-800">
          <AlertCircle className="h-6 w-6" /> Error: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 p-8 text-gray-100">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8 flex items-center gap-3 border-b border-gray-800 pb-4">
          <div className="bg-blue-500/20 p-2 rounded-lg">
            <Users className="h-8 w-8 text-blue-400" />
          </div>
          <h1 className="text-3xl font-bold text-white">Personal Técnico</h1>
        </header>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {tecnicos?.map((tecnico) => (
            <div 
              key={tecnico.id} 
              className={`p-4 rounded-xl border ${
                tecnico.disponible 
                  ? 'bg-gray-800 border-gray-700 hover:border-blue-500/50' 
                  : 'bg-gray-800/50 border-red-900/30 opacity-75'
              } transition-all shadow-lg`}
            >
              <div className="flex justify-between items-start mb-3">
                <h2 className="text-lg font-semibold text-white">{tecnico.nombre}</h2>
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                  tecnico.disponible 
                    ? 'bg-green-500/20 text-green-400 border border-green-500/30' 
                    : 'bg-red-500/20 text-red-400 border border-red-500/30'
                }`}>
                  {tecnico.disponible ? 'Disponible' : 'Ocupado'}
                </span>
              </div>
              
              <div className="space-y-2 text-sm text-gray-400">
                <p className="flex items-center gap-2">
                  <span className="text-gray-500">Especialidad:</span> 
                  <span className="text-gray-300">{tecnico.especialidad}</span>
                </p>
                <p className="flex items-center gap-2">
                  <span className="text-gray-500">RUT:</span> 
                  {tecnico.rut}
                </p>
                <p className="flex items-center gap-2">
                  <span className="text-gray-500">Teléfono:</span> 
                  {tecnico.telefono}
                </p>
              </div>
            </div>
          ))}
        </div>

        {tecnicos?.length === 0 && (
            <p className="text-center text-gray-500 py-10 text-lg">
              No hay técnicos registrados.
            </p>
        )}
      </div>
    </div>
  );
}