import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

rinjani = Document(
    page_content="Gunung Rinjani adalah gunung berapi aktif di pulau Lombok, Nusa Tenggara Barat, Indonesia. Gunung ini menjadi salah satu destinasi wisata pendakian favorit karena memiliki pemandangan yang spektakuler, seperti Danau Segara Anak yang berada di kalderanya. Pesona Rinjani menarik banyak pendaki lokal maupun mancanegara. Di sekitar kawah Rinjani, terdapat sumber air panas yang dipercaya memiliki khasiat penyembuhan. Banyak pengunjung juga mendirikan kemah di tepi danau untuk menikmati pemandangan matahari terbit.",
    metadata={"title": "Gunung Rinjani", "url": "https://id.wikipedia.org/wiki/Gunung_Rinjani"}
)

alaspurwo = Document(
    page_content="Taman Nasional Alas Purwo terletak di Semenanjung Blambangan, Kabupaten Banyuwangi, Jawa Timur. Hutan ini terkenal dengan berbagai misteri dan mitos lokal. Masyarakat setempat menganggap Alas Purwo sebagai hutan paling angker di Pulau Jawa dan merupakan tempat persembunyian gaib. Meski sarat akan cerita mistis dan misteri keunikan spiritualnya, Alas Purwo menawarkan pesona alam yang luar biasa, mulai dari savana Sadengan, Pantai Plengkung (G-Land) yang terkenal untuk berselancar, hingga habitat banteng Jawa dan merak hijau.",
    metadata={"title": "Alas Purwo", "url": "https://id.wikipedia.org/wiki/Taman_Nasional_Alas_Purwo"}
)

pempek = Document(
    page_content="Pempek adalah makanan khas dari Palembang, Sumatera Selatan, yang terbuat dari campuran daging ikan giling dan tepung kanji. Makanan ini disajikan dengan kuah cuka cair berwarna hitam kecokelatan yang rasanya asam, manis, dan pedas (cuko). Ada berbagai jenis pempek, seperti pempek kapal selam (berisi telur), lenjer, dan adaan. Pempek sering disebut sebagai peninggalan kuliner bersejarah dan menjadi favorit masyarakat Indonesia.",
    metadata={"title": "Pempek Palembang", "url": "https://id.wikipedia.org/wiki/Pempek"}
)

gudeg = Document(
    page_content="Gudeg adalah makanan tradisional khas Yogyakarta dan Jawa Tengah yang terbuat dari nangka muda yang dimasak dengan santan selama berjam-jam. Proses memasak yang lama membuat nangka menjadi empuk dan bumbu meresap sempurna, memberikan warna kecokelatan yang khas dari daun jati. Gudeg biasanya disajikan dengan nasi, ayam kampung, telur rebus, tahu, tempe, dan sambal goreng krecek.",
    metadata={"title": "Gudeg", "url": "https://id.wikipedia.org/wiki/Gudeg"}
)


print("Menyimpan ke PGVector...")
db = PGVector.from_documents(
    documents=[rinjani, alaspurwo, pempek, gudeg],
    embedding=embeddings,
    collection_name="wiki_travelista",
    connection_string=DATABASE_URL,
    pre_delete_collection=True
)

print("Verifikasi pencarian Rinjani:", len(db.similarity_search("Rinjani")))
print("Selesai! Database siap!")
