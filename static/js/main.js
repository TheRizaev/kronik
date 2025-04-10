// Данные видео для подгрузки
const videoData = [
    {
        id: 1,
        title: "Основы машинного обучения: Введение в нейронные сети",
        channel: "ИИ Академия",
        views: "245K просмотров",
        age: "1 неделя назад",
        duration: "28:45",
        preview: "1.jpg"
    },
    {
        id: 2,
        title: "Интегральное исчисление: Основные методы и примеры",
        channel: "Математический канал",
        views: "189K просмотров",
        age: "2 недели назад",
        duration: "42:18",
        preview: "2.jpg"
    },
    {
        id: 3,
        title: "Python для анализа данных: Pandas и NumPy",
        channel: "Python Практикум",
        views: "423K просмотров",
        age: "3 дня назад",
        duration: "35:12",
        preview: "3.jpg"
    },
    {
        id: 4,
        title: "Квантовая физика: Принцип неопределенности Гейзенберга",
        channel: "Физика для всех",
        views: "156K просмотров",
        age: "1 день назад",
        duration: "45:23",
        preview: "4.jpg"
    },
    {
        id: 5,
        title: "Основы генетики: От Менделя до современности",
        channel: "Биология и генетика",
        views: "112K просмотров",
        age: "5 дней назад",
        duration: "32:49",
        preview: "5.jpg"
    },
    {
        id: 6,
        title: "История Древнего Рима: От республики к империи",
        channel: "Исторический лекторий",
        views: "174K просмотров",
        age: "2 дня назад",
        duration: "38:17",
        preview: "6.jpg"
    },
    {
        id: 7,
        title: "Микро- и макроэкономика: Основные концепции и модели",
        channel: "Экономика для всех",
        views: "145K просмотров",
        age: "4 дня назад",
        duration: "26:35",
        preview: "7.jpg"
    },
    {
        id: 8,
        title: "Основы органической химии: Функциональные группы",
        channel: "Химия и жизнь",
        views: "132K просмотров",
        age: "6 дней назад",
        duration: "41:52",
        preview: "8.jpg"
    },
    {
        id: 9,
        title: "JavaScript продвинутый уровень: Асинхронное программирование",
        channel: "WebDev Мастер",
        views: "210К просмотров",
        age: "2 дня назад",
        duration: "47:21",
        preview: "9.jpg"
    },
    {
        id: 10,
        title: "Астрономия: Черные дыры и их свойства",
        channel: "Космос и наука",
        views: "328К просмотров",
        age: "5 дней назад",
        duration: "34:17",
        preview: "10.jpg"
    },
    {
        id: 11,
        title: "Линейная алгебра: Векторные пространства",
        channel: "Математический канал",
        views: "167K просмотров",
        age: "3 дня назад",
        duration: "39:45",
        preview: "11.jpg"
    },
    {
        id: 12,
        title: "React и Redux: Управление состоянием приложения",
        channel: "Frontend разработка",
        views: "198K просмотров",
        age: "1 неделя назад",
        duration: "53:28",
        preview: "12.jpg"
    },
    {
        id: 13,
        title: "Биохимия: Метаболические пути в клетке",
        channel: "Биомед",
        views: "98K просмотров",
        age: "4 дня назад",
        duration: "46:39",
        preview: "13.jpg"
    },
    {
        id: 14,
        title: "Дифференциальные уравнения: Практическое применение",
        channel: "Инженерные науки",
        views: "147K просмотров",
        age: "2 недели назад",
        duration: "57:12",
        preview: "14.jpg"
    },
    {
        id: 15,
        title: "Искусственный интеллект: Глубокое обучение",
        channel: "ИИ Академия",
        views: "287K просмотров",
        age: "3 дня назад",
        duration: "41:05",
        preview: "15.jpg"
    },
    {
        id: 16,
        title: "SQL для начинающих: Работа с базами данных",
        channel: "Программирование с нуля",
        views: "201K просмотров",
        age: "1 неделя назад",
        duration: "32:56",
        preview: "16.jpg"
    },
    {
        id: 17,
        title: "Античная философия: От Сократа до Аристотеля",
        channel: "Философские беседы",
        views: "114K просмотров",
        age: "5 дней назад",
        duration: "48:34",
        preview: "17.jpg"
    },
    {
        id: 18,
        title: "Теория вероятностей: Основные концепции",
        channel: "Статистика и анализ",
        views: "132K просмотров",
        age: "6 дней назад",
        duration: "37:18",
        preview: "18.jpg"
    },
    {
        id: 19,
        title: "Анатомия человека: Нервная система",
        channel: "Медицинский портал",
        views: "178K просмотров",
        age: "4 дня назад",
        duration: "44:10",
        preview: "19.jpg"
    },
    {
        id: 20,
        title: "HTML и CSS: Создание адаптивных веб-страниц",
        channel: "WebDev Мастер",
        views: "224K просмотров",
        age: "2 недели назад",
        duration: "36:45",
        preview: "20.jpg"
    }
];

// Делаем данные видео доступными глобально для использования на странице видео
window.videoData = videoData;

// Функция для создания карточки видео
function createVideoCard(videoData, delay = 0) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.style.animationDelay = `${delay}ms`;
    
    // Добавляем обработчик клика, который перенаправляет на страницу видео
    card.onclick = function() {
        window.location.href = `/video/${videoData.id}/`;
    };

    // Определяем путь к превью, с запасным вариантом
    const previewPath = videoData.preview ? 
        `/static/previews/${videoData.preview}` : 
        `/static/placeholder.jpg`;

    card.innerHTML = `
        <div class="thumbnail">
            <img src="${previewPath}" onerror="this.src='/static/placeholder.jpg'" alt="${videoData.title}">
            <div class="duration">${videoData.duration}</div>
        </div>
        <div class="video-info">
            <div class="video-title">${videoData.title}</div>
            <div class="channel-name">${videoData.channel}</div>
            <div class="video-stats">
                <span>${videoData.views}</span>
                <span>• ${videoData.age}</span>
            </div>
        </div>
    `;

    return card;
}

// Переменные для управления загрузкой
let currentIndex = 0;
const videosPerPage = 15;
let loadingSpinner, videosContainer;
let isLoading = false;

// Загрузка первой партии видео
function loadInitialVideos() {
    videosContainer = document.getElementById('videos-container');
    if (!videosContainer) return;
    
    for (let i = 0; i < videosPerPage && i < videoData.length; i++) {
        const card = createVideoCard(videoData[i], i * 100);
        videosContainer.appendChild(card);
        currentIndex++;
    }
}

// Загрузка дополнительных видео
function loadMoreVideos() {
    if (isLoading || currentIndex >= videoData.length) return;
    
    loadingSpinner = document.getElementById('loading-spinner');
    isLoading = true;
    if (loadingSpinner) loadingSpinner.style.display = 'flex';
    
    // Имитация загрузки
    setTimeout(() => {
        const limit = Math.min(currentIndex + videosPerPage, videoData.length);
        
        for (let i = currentIndex; i < limit; i++) {
            const card = createVideoCard(videoData[i], (i - currentIndex) * 100);
            videosContainer.appendChild(card);
        }
        
        currentIndex = limit;
        isLoading = false;
        if (loadingSpinner) loadingSpinner.style.display = 'none';
    }, 1000);
}

// Обработчик прокрутки для бесконечной загрузки
function handleScroll() {
    videosContainer = document.getElementById('videos-container');
    if (!videosContainer) return;
    
    // Проверяем, достиг ли пользователь конца текущих видео
    const lastVideoCard = videosContainer.lastElementChild;
    
    if (lastVideoCard) {
        const lastVideoRect = lastVideoCard.getBoundingClientRect();
        // Загружаем новые видео только когда последняя карточка видео видна в области просмотра
        if (lastVideoRect.bottom <= window.innerHeight && !isLoading) {
            loadMoreVideos();
        }
    }
}

// Функция для поиска видео
function searchVideos(query) {
    if (!query.trim()) return [];
    
    query = query.toLowerCase();
    return videoData.filter(video => 
        video.title.toLowerCase().includes(query) || 
        video.channel.toLowerCase().includes(query)
    );
}

// Функция для отображения результатов поиска в выпадающем списке
function showSearchResults(results, searchDropdown) {
    if (!searchDropdown) return;
    
    searchDropdown.innerHTML = '';
    
    if (results.length === 0) {
        searchDropdown.classList.remove('show');
        return;
    }
    
    // Ограничиваем количество результатов для выпадающего списка
    const displayResults = results.slice(0, 5);
    
    displayResults.forEach(video => {
        // Определяем путь к превью, с запасным вариантом
        const previewPath = video.preview ? 
            `/static/previews/${video.preview}` : 
            `/static/placeholder.jpg`;
            
        const resultItem = document.createElement('div');
        resultItem.className = 'search-result';
        resultItem.innerHTML = `
            <div class="search-thumbnail">
                <img src="${previewPath}" onerror="this.src='/static/placeholder.jpg'" alt="${video.title}">
            </div>
            <div class="search-info">
                <div class="search-title">${video.title}</div>
                <div class="search-channel">${video.channel}</div>
            </div>
        `;
        
        resultItem.addEventListener('click', function() {
            window.location.href = `/video/${video.id}/`;
        });
        
        searchDropdown.appendChild(resultItem);
    });
    
    // Если есть больше результатов, добавляем ссылку "Показать все результаты"
    if (results.length > 5) {
        const showMore = document.createElement('div');
        showMore.className = 'search-more';
        showMore.textContent = 'Показать все результаты';
        
        showMore.addEventListener('click', function() {
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                // Перенаправление на страницу результатов поиска
                window.location.href = `/search?query=${encodeURIComponent(searchInput.value)}`;
            }
        });
        
        searchDropdown.appendChild(showMore);
    }
    
    searchDropdown.classList.add('show');
}

// Функция для настройки поиска
function setupSearch() {
    const searchInput = document.getElementById('search-input');
    const searchDropdown = document.getElementById('search-dropdown');
    const searchButton = document.querySelector('.search-button');
    
    if (!searchInput || !searchDropdown) return;
    
    // Обработчики событий для поиска
    searchInput.addEventListener('input', function() {
        const query = this.value;
        const results = searchVideos(query);
        showSearchResults(results, searchDropdown);
    });
    
    searchInput.addEventListener('focus', function() {
        if (this.value.trim()) {
            const results = searchVideos(this.value);
            showSearchResults(results, searchDropdown);
        }
    });
    
    document.addEventListener('click', function(e) {
        if (searchInput && searchDropdown && 
            !searchInput.contains(e.target) && 
            !searchDropdown.contains(e.target)) {
            searchDropdown.classList.remove('show');
        }
    });
    
    if (searchButton) {
        searchButton.addEventListener('click', function() {
            if (searchInput.value.trim()) {
                window.location.href = `/search?query=${encodeURIComponent(searchInput.value)}`;
            }
        });
    }
    
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && this.value.trim()) {
            window.location.href = `/search?query=${encodeURIComponent(this.value)}`;
        }
    });
}

// Функция для настройки сворачивания/разворачивания боковой панели
function setupSidebar() {
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const mainContainer = document.querySelector('.main-container');
    
    if (!sidebarToggle || !sidebar || !mainContainer) return;
    
    sidebarToggle.addEventListener('click', function() {
        sidebar.classList.toggle('collapsed');
        mainContainer.classList.toggle('expanded');
    });
}

// Function to make sidebar menu items active when clicked
function setupSidebarMenuItems() {
    const menuItems = document.querySelectorAll('.sidebar .menu-item');
    
    if (!menuItems.length) return;
    
    menuItems.forEach(item => {
        // Skip items that already have onclick handlers (like Studio and Home)
        if (item.getAttribute('onclick')) return;
        
        item.addEventListener('click', function() {
            // Remove active class from all items
            menuItems.forEach(i => i.classList.remove('active'));
            // Add active class to clicked item
            this.classList.add('active');
        });
    });
}

// Функция для настройки переключения темы
function setupThemeToggle() {
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const themeTransition = document.querySelector('.theme-transition');
    const toggleText = document.querySelector('.toggle-text');
    
    if (!themeToggle || !themeTransition || !toggleText) return;
    
    themeToggle.addEventListener('click', function() {
        const isDark = body.classList.contains('dark-theme');
        themeTransition.className = `theme-transition ${isDark ? 'light' : 'dark'} animating`;
        
        setTimeout(() => {
            body.classList.toggle('dark-theme');
            body.classList.toggle('light-theme');
        }, 500);
        
        setTimeout(() => {
            themeTransition.classList.remove('animating');
        }, 1500);
    });
}

// Функция для настройки пользовательского меню
function setupUserMenu() {
    const userMenu = document.querySelector('.user-menu');
    const userDropdown = document.querySelector('.user-dropdown');
    
    if (!userMenu || !userDropdown) return;
    
    userMenu.addEventListener('click', function(e) {
        e.stopPropagation();
        userDropdown.classList.toggle('show');
    });
    
    // Закрытие выпадающего меню по клику вне него
    document.addEventListener('click', function(e) {
        if (userMenu && userDropdown && 
            !userMenu.contains(e.target)) {
            userDropdown.classList.remove('show');
        }
    });
}

// Функция для настройки мобильного меню
function setupMobileMenu() {
    const mobileMenuButton = document.querySelector('.mobile-menu-button');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.overlay');
    
    if (!sidebar || !overlay) return;
    
    if (mobileMenuButton) {
        mobileMenuButton.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            overlay.classList.toggle('show');
        });
    }
    
    overlay.addEventListener('click', function() {
        sidebar.classList.remove('show');
        overlay.classList.remove('show');
    });
}

// Функция для настройки категорий
function setupCategories() {
    const categoryChips = document.querySelectorAll('.category-chip');
    videosContainer = document.getElementById('videos-container');
    
    if (!categoryChips.length || !videosContainer) return;
    
    categoryChips.forEach(chip => {
        chip.addEventListener('click', function() {
            // Убираем активный класс у всех элементов
            categoryChips.forEach(c => c.classList.remove('active'));
            // Добавляем активный класс к выбранному элементу
            this.classList.add('active');
            
            // Сбрасываем видео и загружаем новые
            videosContainer.innerHTML = '';
            currentIndex = 0;
            loadInitialVideos();
        });
    });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация DOM-элементов
    loadingSpinner = document.getElementById('loading-spinner');
    videosContainer = document.getElementById('videos-container');
    
    // Инициализация загрузки видео на главной странице
    loadInitialVideos();
    
    // Подписка на прокрутку для бесконечной загрузки
    window.addEventListener('scroll', handleScroll);
    
    // Настройка всех интерактивных элементов
    setupSearch();
    setupSidebar();
    setupThemeToggle();
    setupUserMenu();
    setupMobileMenu();
    setupCategories();
    setupSidebarMenuItems()
});

function setupThemeToggle() {
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const themeTransition = document.querySelector('.theme-transition');
    const toggleText = document.querySelector('.toggle-text');
    
    if (!themeToggle || !themeTransition || !toggleText) return;
    
    // Загружаем сохраненную тему при загрузке страницы
    const savedTheme = localStorage.getItem('kronik-theme');
    if (savedTheme) {
        if (savedTheme === 'light') {
            body.classList.remove('dark-theme');
            body.classList.add('light-theme');
        } else {
            body.classList.remove('light-theme');
            body.classList.add('dark-theme');
        }
    }
    
    themeToggle.addEventListener('click', function() {
        const isDark = body.classList.contains('dark-theme');
        themeTransition.className = `theme-transition ${isDark ? 'light' : 'dark'} animating`;
        
        setTimeout(() => {
            body.classList.toggle('dark-theme');
            body.classList.toggle('light-theme');
            
            // Обновляем текст кнопки
            const newTheme = body.classList.contains('light-theme') ? 'light' : 'dark';
            
            // Сохраняем выбранную тему в localStorage
            localStorage.setItem('kronik-theme', newTheme);
        }, 500);
        
        setTimeout(() => {
            themeTransition.classList.remove('animating');
        }, 1500);
    });
}